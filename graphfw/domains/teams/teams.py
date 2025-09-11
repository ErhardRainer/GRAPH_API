from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

from graphfw.core.http import GraphClient
from graphfw.core.odata import OData


def list_df(
    client: GraphClient,
    user_id: Optional[str] = None,
    top: Optional[int] = None,
    filter: Optional[str] = None,
    orderby: Optional[str] = None,
    search: Optional[str] = None,
    page_size: Optional[int] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    List all Teams visible to the tenant or those joined by a specific user.

    Parameters
    ----------
    client : GraphClient
        Authenticated GraphClient instance.
    user_id : str, optional
        If provided, list only teams joined by this user (via `/users/{id}/joinedTeams`).
        If None, list all tenant teams (`/teams`).
    top : int, optional
        Client-side maximum number of records to return.
    filter : str, optional
        OData $filter expression.
    orderby : str, optional
        OData $orderby expression.
    search : str, optional
        OData $search expression (ConsistencyLevel: eventual will be applied by GraphClient).
    page_size : int, optional
        Preferred page size for server paging.

    Returns
    -------
    (df, info) : Tuple[pandas.DataFrame, dict]
        df : DataFrame
            Deterministic column order: ['id','displayName','description','visibility','createdDateTime'] + extras.
        info : dict
            Diagnostics including `url`, `params`, `attempt`, `retries`, `warnings`.

    Example
    -------
    >>> from graphfw.core.auth import TokenProvider
    >>> from graphfw.core.http import GraphClient
    >>> from graphfw.domains.teams.teams import list_df
    >>>
    >>> tp = TokenProvider.from_json("config.json")
    >>> gc = GraphClient(tp)
    >>> df, info = list_df(gc)
    >>> print(df.head())
    """
    # ----------------------------
    # Helper: deterministic columns
    # ----------------------------
    def _reorder_columns(records: List[Dict[str, Any]]) -> pd.DataFrame:
        preferred = ["id", "displayName", "description", "visibility", "createdDateTime"]
        if not records:
            return pd.DataFrame(columns=preferred)
        df_local = pd.DataFrame(records)
        cols = [c for c in preferred if c in df_local.columns] + [c for c in df_local.columns if c not in preferred]
        return df_local[cols]

    # ----------------------------
    # Build URL and params
    # ----------------------------
    url = f"/users/{user_id}/joinedTeams" if user_id else "/teams"

    odata = OData(
        filter=filter,
        orderby=orderby,
        search=search,
        top=top,
        page_size=page_size,
    )
    params = odata.to_params()

    # ----------------------------
    # Call Graph API
    # ----------------------------
    items, info = client.get_paged(url, params=params, top=top, search=search)

    # ----------------------------
    # Build DataFrame
    # ----------------------------
    df = _reorder_columns(items)

    info.update(
        {
            "url": url,
            "params": params,
            "mapping_table": None,
            "resolution_report": None,
            "tz_policy": None,
        }
    )
    return df, info


def get_by_id_df(
    client: GraphClient,
    team_id: str,
    select: Optional[str] = None,
    expand: Optional[str] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Get a single Team by its ID and return as a one-row DataFrame.

    Parameters
    ----------
    client : GraphClient
        Authenticated GraphClient instance.
    team_id : str
        The Team (Group) ID.
    select : str, optional
        OData $select expression (comma-separated fields).
    expand : str, optional
        OData $expand expression (comma-separated navigations).

    Returns
    -------
    (df, info) : Tuple[pandas.DataFrame, dict]
        df : DataFrame
            One-row DataFrame with deterministic columns:
            ['id','displayName','description','visibility','createdDateTime'] + extras.
        info : dict
            Diagnostics including `url`, `params`, `attempt`, `retries`, `warnings`.

    Notes
    -----
    * Uses Graph endpoint: `/teams/{team-id}`.
    * If `select` is not provided, default Graph response fields are returned.
    * Timezone normalization is not applied here (Teams timestamps are returned as-is).

    Example
    -------
    >>> from graphfw.core.auth import TokenProvider
    >>> from graphfw.core.http import GraphClient
    >>> from graphfw.domains.teams.teams import get_by_id_df
    >>>
    >>> tp = TokenProvider.from_json("config.json")
    >>> gc = GraphClient(tp)
    >>> df, info = get_by_id_df(gc, team_id="00000000-0000-0000-0000-000000000000")
    >>> print(df.loc[0, "displayName"])
    """
    # ----------------------------
    # Helper: deterministic columns
    # ----------------------------
    def _reorder_one(record: Dict[str, Any]) -> pd.DataFrame:
        preferred = ["id", "displayName", "description", "visibility", "createdDateTime"]
        df_local = pd.DataFrame([record] if record else [])
        if df_local.empty:
            return pd.DataFrame(columns=preferred)
        cols = [c for c in preferred if c in df_local.columns] + [c for c in df_local.columns if c not in preferred]
        return df_local[cols]

    # ----------------------------
    # Build URL and params
    # ----------------------------
    url = f"/teams/{team_id}"
    odata = OData(select=select, expand=expand)
    params = odata.to_params()

    # ----------------------------
    # Call Graph API
    # ----------------------------
    item, info = client.get(url, params=params)

    # ----------------------------
    # Build DataFrame
    # ----------------------------
    df = _reorder_one(item)

    info.update(
        {
            "url": url,
            "params": params,
            "mapping_table": None,
            "resolution_report": None,
            "tz_policy": None,
        }
    )
    return df, info
