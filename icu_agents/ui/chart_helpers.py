"""Interactive Plotly charts for point-in-time ICU views."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


SEVERITY_COLORS = {
    "stable": "#2ecc71",
    "worsening": "#f39c12",
    "critical": "#e74c3c",
}

CATEGORY_COLORS = {
    "admission": "#95a5a6",
    "vitals": "#e74c3c",
    "lab": "#3498db",
    "note": "#9b59b6",
    "respiratory": "#16a085",
}

SCRUBBABLE_CHART_KEYS = (
    "overview_vitals_chart",
    "overview_temp_chart",
    "vitals_detail_chart",
    "lab_events_chart",
    "overview_events_chart",
    "clinical_events_chart",
)


def sync_hour_from_chart_selection(chart_key: str, hours: List[int]) -> None:
    """Update the shared ICU hour slider when the user clicks a chart point."""
    import json

    event = st_session_get(chart_key)
    if event is None:
        return

    points: List[Dict[str, Any]] = []
    if hasattr(event, "selection") and event.selection is not None:
        points = list(event.selection.points or [])
    elif isinstance(event, dict):
        points = list(event.get("selection", {}).get("points", []))

    if not points:
        return

    point = points[0]
    hour_value = point.get("customdata", point.get("x"))
    try:
        clicked = int(round(float(hour_value)))
    except (TypeError, ValueError):
        return

    valid = sorted({int(h) for h in hours})
    closest = min(valid, key=lambda hour: abs(hour - clicked))

    token = json.dumps(point, sort_keys=True, default=str)
    sync_key = f"_synced_{chart_key}"
    if st_session_get(sync_key) == token:
        return

    st_session_set("pit_hour_slider", closest)
    st_session_set(sync_key, token)


def clear_chart_sync_tokens() -> None:
    import streamlit as st

    for chart_key in SCRUBBABLE_CHART_KEYS:
        sync_key = f"_synced_{chart_key}"
        if sync_key in st.session_state:
            del st.session_state[sync_key]


def st_session_get(key: str) -> Any:
    import streamlit as st

    return st.session_state.get(key)


def st_session_set(key: str, value: Any) -> None:
    import streamlit as st

    st.session_state[key] = value


def _hour_marker(fig: go.Figure, selected_hour: int, row: Optional[int] = None, col: Optional[int] = None) -> None:
    line_kw = {"line_dash": "dash", "line_color": "#2c3e50", "line_width": 2, "opacity": 0.8}
    if row is not None and col is not None:
        fig.add_vline(x=selected_hour, row=row, col=col, **line_kw)
    else:
        fig.add_vline(x=selected_hour, **line_kw)


def _highlight_point(fig: go.Figure, df: pd.DataFrame, selected_hour: int, y_col: str, row: int, col: int = 1) -> None:
    match = df[df["hour"] == selected_hour]
    if match.empty or y_col not in match.columns:
        return
    fig.add_trace(
        go.Scatter(
            x=match["hour"],
            y=match[y_col],
            mode="markers",
            marker={"size": 14, "color": "#2c3e50", "symbol": "circle-open", "line_width": 3},
            name=f"@ hour {selected_hour}",
            showlegend=False,
            hovertemplate=f"Hour {selected_hour}<br>{y_col}: %{{y}}<extra></extra>",
        ),
        row=row,
        col=col,
    )


def build_vitals_figure(df_v: pd.DataFrame, selected_hour: int) -> go.Figure:
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=("Heart rate", "SpO₂", "Resp rate & SBP"),
    )

    fig.add_trace(
        go.Scatter(
            x=df_v["hour"],
            y=df_v["heart_rate"],
            customdata=df_v["hour"],
            mode="lines+markers",
            name="Heart rate",
            line={"color": "#e74c3c", "width": 2},
            marker={"size": 7},
            hovertemplate="Hour %{x}<br>HR %{y} bpm<extra></extra>",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df_v["hour"],
            y=df_v["spo2"],
            customdata=df_v["hour"],
            mode="lines+markers",
            name="SpO₂",
            line={"color": "#3498db", "width": 2},
            marker={"size": 7},
            hovertemplate="Hour %{x}<br>SpO₂ %{y}%<extra></extra>",
        ),
        row=2,
        col=1,
    )
    if "resp_rate" in df_v.columns:
        fig.add_trace(
            go.Scatter(
                x=df_v["hour"],
                y=df_v["resp_rate"],
                customdata=df_v["hour"],
                mode="lines+markers",
                name="Resp rate",
                line={"color": "#9b59b6", "width": 2},
                marker={"size": 7},
                hovertemplate="Hour %{x}<br>RR %{y}/min<extra></extra>",
            ),
            row=3,
            col=1,
        )
    if "systolic_bp" in df_v.columns:
        fig.add_trace(
            go.Scatter(
                x=df_v["hour"],
                y=df_v["systolic_bp"],
                customdata=df_v["hour"],
                mode="lines+markers",
                name="SBP",
                line={"color": "#16a085", "width": 2, "dash": "dot"},
                marker={"size": 6, "symbol": "square"},
                hovertemplate="Hour %{x}<br>SBP %{y} mmHg<extra></extra>",
            ),
            row=3,
            col=1,
        )

    for row, col_name in ((1, "heart_rate"), (2, "spo2"), (3, "resp_rate")):
        _hour_marker(fig, selected_hour, row=row, col=1)
        if col_name in df_v.columns:
            _highlight_point(fig, df_v, selected_hour, col_name, row=row, col=1)

    fig.update_layout(
        height=720,
        title=f"Vitals through ICU hour {selected_hour} — click a point to scrub time",
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
        margin={"t": 80, "b": 40},
    )
    fig.update_xaxes(title_text="ICU hour", row=3, col=1)
    return fig


def build_overview_vitals_figure(df_v: pd.DataFrame, selected_hour: int) -> go.Figure:
    fig = go.Figure()
    for col, color, label in (
        ("heart_rate", "#e74c3c", "Heart rate"),
        ("spo2", "#3498db", "SpO₂"),
        ("resp_rate", "#9b59b6", "Resp rate"),
    ):
        if col not in df_v.columns:
            continue
        fig.add_trace(
            go.Scatter(
                x=df_v["hour"],
                y=df_v[col],
                customdata=df_v["hour"],
                mode="lines+markers",
                name=label,
                line={"width": 2},
                marker={"size": 6},
                hovertemplate=f"Hour %{{x}}<br>{label} %{{y}}<extra></extra>",
            )
        )

    _hour_marker(fig, selected_hour)
    for col in ("heart_rate", "spo2", "resp_rate"):
        if col in df_v.columns:
            match = df_v[df_v["hour"] == selected_hour]
            if not match.empty:
                fig.add_trace(
                    go.Scatter(
                        x=match["hour"],
                        y=match[col],
                        mode="markers",
                        marker={"size": 12, "symbol": "circle-open", "line_width": 2},
                        showlegend=False,
                        hoverinfo="skip",
                    )
                )

    fig.update_layout(
        height=360,
        title=f"Overview vitals · hour {selected_hour} selected",
        xaxis_title="ICU hour",
        hovermode="x unified",
        legend={"orientation": "h", "y": 1.15},
        margin={"t": 60},
    )
    return fig


def build_temperature_figure(df_v: pd.DataFrame, selected_hour: int) -> go.Figure:
    fig = go.Figure()
    if "temperature" not in df_v.columns:
        return fig

    fig.add_trace(
        go.Scatter(
            x=df_v["hour"],
            y=df_v["temperature"],
            customdata=df_v["hour"],
            mode="lines+markers",
            fill="tozeroy",
            name="Temperature",
            line={"color": "#e67e22", "width": 2},
            marker={"size": 6},
            hovertemplate="Hour %{x}<br>Temp %{y}°F<extra></extra>",
        )
    )
    _hour_marker(fig, selected_hour)
    match = df_v[df_v["hour"] == selected_hour]
    if not match.empty:
        fig.add_trace(
            go.Scatter(
                x=match["hour"],
                y=match["temperature"],
                mode="markers",
                marker={"size": 12, "symbol": "circle-open", "line_width": 2},
                showlegend=False,
                hoverinfo="skip",
            )
        )
    fig.update_layout(
        height=360,
        title=f"Temperature · hour {selected_hour}",
        xaxis_title="ICU hour",
        margin={"t": 60},
    )
    return fig


def build_labs_bar_figure(labs: Dict[str, float], selected_hour: int, within_screen_fn) -> go.Figure:
    names = list(labs.keys())
    values = list(labs.values())
    colors = [
        "#2ecc71" if within_screen_fn(name, value) else "#e74c3c"
        for name, value in labs.items()
    ]
    fig = go.Figure(
        go.Bar(
            x=names,
            y=values,
            marker_color=colors,
            customdata=[[selected_hour]] * len(names),
            hovertemplate="Hour %{customdata[0]}<br>%{x}: %{y}<extra></extra>",
        )
    )
    fig.update_layout(
        height=320,
        title=f"Lab panel at ICU hour {selected_hour}",
        xaxis_title="Analyte",
        yaxis_title="Value",
        margin={"t": 60},
    )
    return fig


def build_risk_bar_figure(risk: Dict[str, float], selected_hour: int) -> go.Figure:
    fig = go.Figure(
        go.Bar(
            x=list(risk.keys()),
            y=list(risk.values()),
            marker_color="#8e44ad",
            customdata=[[selected_hour]] * len(risk),
            hovertemplate="Hour %{customdata[0]}<br>%{x}: %{y}%<extra></extra>",
        )
    )
    fig.update_layout(
        height=300,
        title=f"Risk scores at ICU hour {selected_hour}",
        yaxis_title="Score (%)",
        margin={"t": 60},
    )
    return fig


def build_lab_events_figure(lab_events: List[Dict[str, Any]], selected_hour: int) -> go.Figure:
    visible = [event for event in lab_events if event["hour"] <= selected_hour]
    if not visible:
        fig = go.Figure()
        fig.update_layout(title=f"No lab draws recorded by hour {selected_hour}", height=280)
        return fig

    fig = go.Figure()
    for analyte in sorted({event["analyte"] for event in visible}):
        rows = [event for event in visible if event["analyte"] == analyte]
        fig.add_trace(
            go.Scatter(
                x=[event["hour"] for event in rows],
                y=[event["value"] for event in rows],
                customdata=[event["hour"] for event in rows],
                mode="lines+markers",
                name=analyte,
                hovertemplate="Hour %{x}<br>%{fullData.name}: %{y}<extra></extra>",
            )
        )
    _hour_marker(fig, selected_hour)
    fig.update_layout(
        height=320,
        title=f"Lab draws over time (through hour {selected_hour})",
        xaxis_title="ICU hour",
        yaxis_title="Value",
        hovermode="x unified",
        margin={"t": 60},
    )
    return fig


def build_events_timeline_figure(events: List[Dict[str, Any]], selected_hour: int) -> go.Figure:
    visible = [event for event in events if event["hour"] <= selected_hour]
    if not visible:
        fig = go.Figure()
        fig.update_layout(title=f"No events by hour {selected_hour}", height=320)
        return fig

    categories = sorted({event.get("category", "other") for event in visible})
    y_map = {cat: idx for idx, cat in enumerate(categories)}

    fig = go.Figure()
    for category in categories:
        rows = [event for event in visible if event.get("category") == category]
        fig.add_trace(
            go.Scatter(
                x=[event["hour"] for event in rows],
                y=[y_map[category]] * len(rows),
                customdata=[event["hour"] for event in rows],
                mode="markers",
                name=category,
                marker={
                    "size": 12,
                    "color": CATEGORY_COLORS.get(category, "#7f8c8d"),
                    "symbol": "circle",
                },
                text=[event.get("summary", "") for event in rows],
                hovertemplate="Hour %{x}<br>%{text}<extra></extra>",
            )
        )

    _hour_marker(fig, selected_hour)
    fig.update_layout(
        height=360,
        title=f"Clinical events timeline (hours 0–{selected_hour})",
        xaxis_title="ICU hour",
        yaxis={
            "tickmode": "array",
            "tickvals": list(y_map.values()),
            "ticktext": list(y_map.keys()),
        },
        margin={"t": 60},
    )
    return fig


def render_scrubbable_chart(fig: go.Figure, chart_key: str) -> None:
    """Render a Plotly chart; clicking a point reruns and updates the ICU hour slider."""
    import streamlit as st

    st.plotly_chart(
        fig,
        use_container_width=True,
        on_select="rerun",
        selection_mode="points",
        key=chart_key,
    )


def render_static_chart(fig: go.Figure, chart_key: str) -> None:
    import streamlit as st

    st.plotly_chart(fig, use_container_width=True, key=chart_key)
