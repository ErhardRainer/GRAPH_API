from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


@dataclass(frozen=True)
class ResolutionInfo:
    """
    Diagnostics for a config selection operation.
    """
    file_path: Optional[str]
    requested_path: str
    resolved_path: str
    tried_paths: Tuple[str, ...]
    requested_keys: Tuple[str, ...]
    found_keys: Tuple[str, ...]
    warnings: Tuple[str, ...]


def load_config(file_path: str | Path) -> Dict[str, Any]:
    """
    Load a JSON configuration file.

    Parameters
    ----------
    file_path : str | Path
        Path to a JSON file.

    Returns
    -------
    dict
        Parsed JSON object.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    json.JSONDecodeError
        If the JSON cannot be parsed.
    """
    p = Path(file_path)
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def select_values_from_file(
    file_path: str | Path,
    path: str,
    keys: Sequence[str],
    *,
    strict: bool = False,
) -> Tuple[Tuple[Any, ...], Dict[str, Any]]:
    """
    Convenience wrapper of `select_values` that loads the config file first.

    Parameters
    ----------
    file_path : str | Path
        Path to the JSON config.
    path : str
        Dot path to the object (e.g. "sharepoint.list1" or "sharepoint.lists.list1").
    keys : Sequence[str]
        Keys to extract, in order.
    strict : bool, default False
        If True, missing path/keys raise ValueError. Otherwise, missing keys -> None.

    Returns
    -------
    (values, info) : Tuple[Tuple[Any, ...], Dict[str, Any]]
    """
    cfg = load_config(file_path)
    return select_values(cfg, path=path, keys=keys, file_path=str(file_path), strict=strict)


def select_values(
    config: Mapping[str, Any],
    *,
    path: str,
    keys: Sequence[str],
    file_path: Optional[str] = None,
    strict: bool = False,
) -> Tuple[Tuple[Any, ...], Dict[str, Any]]:
    """
    Read specific elements from a nested configuration using a dot-path with
    light heuristics for SharePoint-style list addressing.

    Supports both:
      - `sharepoint.list1`
      - `sharepoint.lists.list1`

    Works with any number of keys — 1, 2, 10, ... —
    the returned tuple follows the same order as `keys` for easy multiple assignment.

    Parameters
    ----------
    config : Mapping[str, Any]
        Parsed JSON configuration (e.g., from `load_config`).
    path : str
        Dot-separated path to a nested object.
    keys : Sequence[str]
        Keys to extract from the resolved object, in order.
    file_path : Optional[str], default None
        Path to the source JSON file (for diagnostics only).
    strict : bool, default False
        If True, missing path segments or keys raise a ValueError.
        If False, missing keys are returned as None and warnings are reported.

    Returns
    -------
    (values, info) : Tuple[Tuple[Any, ...], Dict[str, Any]]
        values : tuple
            Tuple of values matching the `keys` order.
        info : dict
            Diagnostics incl. requested/resolved paths, found keys, and warnings.
    """
    # --- helpers -------------------------------------------------------------

    def _sanitize_key(k: str) -> str:
        return k.replace("-", "_").replace(" ", "_").lower()

    def _camel_to_snake(name: str) -> str:
        out: List[str] = []
        for ch in name:
            if ch.isupper():
                out.append("_")
                out.append(ch.lower())
            else:
                out.append(ch)
        return "".join(out).strip("_")

    def _candidate_key_forms(k: str) -> List[str]:
        forms = [k]
        snake = _camel_to_snake(k)
        if snake != k:
            forms.append(snake)
        forms.append(k.replace("-", "_"))
        forms.append(k.replace("_", ""))
        forms.append(_sanitize_key(k))
        if k.lower() == "site_url":
            forms += ["siteUrl", "siteurl"]
        return list(dict.fromkeys(forms))  # unique, keep order

    def _dict_get_lenient(d: Mapping[str, Any], seg: str) -> Optional[str]:
        if seg in d:
            return seg
        target = _sanitize_key(seg)
        for k in d.keys():
            if _sanitize_key(k) == target:
                return k
        return None

    def _resolve_object_with_heuristics(
        cfg: Mapping[str, Any], dot_path: str
    ) -> Tuple[Optional[Mapping[str, Any]], str, Tuple[str, ...], List[str]]:
        warnings: List[str] = []
        tried: List[str] = []

        segs = [s for s in dot_path.split(".") if s]
        candidates: List[List[str]] = []

        # 1) as-is
        candidates.append(segs[:])

        # 2) inject 'lists' after first if not present
        if len(segs) >= 2 and segs[1] not in ("lists", "list"):
            candidates.append(segs[:1] + ["lists"] + segs[1:])

        # 3) pluralize/singularize toggles
        if len(segs) >= 2:
            if segs[1] == "list":
                cand = segs[:]
                cand[1] = "lists"
                candidates.append(cand)
            if segs[1] == "lists":
                cand = segs[:]
                cand[1] = "list"
                candidates.append(cand)

        seen: set[Tuple[str, ...]] = set()
        uniq: List[List[str]] = []
        for c in candidates:
            t = tuple(c)
            if t not in seen:
                seen.add(t)
                uniq.append(c)

        for cand in uniq:
            path_str = ".".join(cand)
            tried.append(path_str)
            cur: Any = cfg
            actual_segments: List[str] = []
            ok = True
            for seg in cand:
                if not isinstance(cur, Mapping):
                    ok = False
                    break
                actual = _dict_get_lenient(cur, seg)
                if actual is None:
                    ok = False
                    break
                actual_segments.append(actual)
                cur = cur[actual]
            if ok and isinstance(cur, Mapping):
                return cur, ".".join(actual_segments), tuple(tried), warnings

        warnings.append(f"Path could not be resolved (tried: {', '.join(tried)}).")
        return None, "", tuple(tried), warnings

    def _pick_values(
        obj: Mapping[str, Any], wanted_keys: Sequence[str]
    ) -> Tuple[Tuple[Any, ...], List[str], List[str]]:
        values: List[Any] = []
        found_keys: List[str] = []
        warns: List[str] = []
        index: Dict[str, str] = {_sanitize_key(k): k for k in obj.keys()}

        for w in wanted_keys:
            actual_key: Optional[str] = None
            for cand in _candidate_key_forms(w):
                if cand in obj:
                    actual_key = cand
                    break
                sk = _sanitize_key(cand)
                if sk in index:
                    actual_key = index[sk]
                    break
            if actual_key is None:
                if strict:
                    raise ValueError(f"Key '{w}' not found in object (available: {list(obj.keys())})")
                values.append(None)
                found_keys.append("")
                warns.append(f"Key '{w}' not found; returned None.")
            else:
                values.append(obj[actual_key])
                found_keys.append(actual_key)
        return tuple(values), found_keys, warns

    # --- resolve object ------------------------------------------------------

    obj, resolved_path, tried_paths, path_warnings = _resolve_object_with_heuristics(config, path)
    warnings: List[str] = list(path_warnings)

    if obj is None:
        if strict:
            raise ValueError(f"Path '{path}' could not be resolved. Tried: {', '.join(tried_paths)}")
        values = tuple([None] * len(keys))
        info = ResolutionInfo(
            file_path=file_path,
            requested_path=path,
            resolved_path="",
            tried_paths=tried_paths,
            requested_keys=tuple(keys),
            found_keys=tuple([""] * len(keys)),
            warnings=tuple(warnings),
        )
        return values, _info_to_dict(info)

    # --- pick values ---------------------------------------------------------

    values, found_keys, key_warnings = _pick_values(obj, keys)
    warnings.extend(key_warnings)

    info = ResolutionInfo(
        file_path=file_path,
        requested_path=path,
        resolved_path=resolved_path,
        tried_paths=tried_paths,
        requested_keys=tuple(keys),
        found_keys=tuple(found_keys),
        warnings=tuple(warnings),
    )
    return values, _info_to_dict(info)


def select_dict_from_file(
    file_path: str | Path,
    path: str,
    keys: Sequence[str],
    *,
    strict: bool = False,
    defaults: Optional[Mapping[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Load config and return a dict keyed by the requested `keys`.

    Missing keys yield `None` (or `defaults[key]` if provided) unless `strict=True`.

    Returns
    -------
    (result, info) : Tuple[Dict[str, Any], Dict[str, Any]]
        result : dict
            Maps each requested key -> value (preserves input order).
        info : dict
            Same diagnostics as `select_values`.
    """
    cfg = load_config(file_path)
    return select_dict(cfg, path=path, keys=keys, file_path=str(file_path), strict=strict, defaults=defaults)


def select_dict(
    config: Mapping[str, Any],
    *,
    path: str,
    keys: Sequence[str],
    file_path: Optional[str] = None,
    strict: bool = False,
    defaults: Optional[Mapping[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Like `select_values` but returns a dict `{requested_key: value}`.

    Parameters
    ----------
    config : Mapping[str, Any]
        Parsed config.
    path : str
        Dot path to the object.
    keys : Sequence[str]
        Keys to extract (any length).
    file_path : Optional[str], default None
        For diagnostics.
    strict : bool, default False
        If True, missing keys raise ValueError.
    defaults : Optional[Mapping[str, Any]], default None
        Optional fallback values per key (used only when key is missing and strict=False).

    Returns
    -------
    (result, info) : Tuple[Dict[str, Any], Dict[str, Any]]
    """
    values, info = select_values(
        config, path=path, keys=keys, file_path=file_path, strict=strict
    )
    result: Dict[str, Any] = {}
    for k, v in zip(keys, values):
        if v is None and not strict and defaults and k in defaults:
            result[k] = defaults[k]
        else:
            result[k] = v
    return result, info


def _info_to_dict(info: ResolutionInfo) -> Dict[str, Any]:
    """Convert ResolutionInfo dataclass to a plain dict."""
    return {
        "file_path": info.file_path,
        "requested_path": info.requested_path,
        "resolved_path": info.resolved_path,
        "tried_paths": list(info.tried_paths),
        "requested_keys": list(info.requested_keys),
        "found_keys": list(info.found_keys),
        "warnings": list(info.warnings),
    }
