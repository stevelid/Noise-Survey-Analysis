"""Small, fixed-scale plots for the survey's configured weather source."""
import pandas as pd
from bokeh.layouts import column
from bokeh.models import (
    BasicTicker, BoxSelectTool, ColumnDataSource, CustomJS, FixedTicker,
    HoverTool, LinearAxis, PanTool, Range1d, Span, WheelZoomTool,
)
from bokeh.plotting import figure

from noise_survey_analysis.core.config import FRAME_BORDER_LEFT

WEATHER_BORDER_RIGHT = 56
COMPASS = "N NNE NE ENE E ESE SE SSE S SSW SW WSW W WNW NW NNW".split()
WIND_COLOR = "#18597e"
GUST_COLOR = "#66859f"
RAIN_COLOR = "#167669"
DIRECTION_COLOR = "#77418d"


def _plot(name, x_range, **kwargs):
    pan, zoom = PanTool(dimensions="width"), WheelZoomTool(dimensions="width")
    plot = figure(
        name=name, x_axis_type="datetime", x_range=x_range, sizing_mode="stretch_width",
        min_border_left=FRAME_BORDER_LEFT, min_border_right=WEATHER_BORDER_RIGHT,
        min_border_top=2, min_border_bottom=2, margin=0, toolbar_location=None,
        tools=[pan, BoxSelectTool(dimensions="width"), zoom], active_drag=pan, active_scroll=zoom, **kwargs,
    )
    plot.axis.axis_label_text_font_size = "10px"
    plot.axis.axis_label_text_font_style = "normal"
    plot.axis.major_label_text_font_size = "9px"
    plot.grid.grid_line_color = "#e4ebf2"
    plot.outline_line_color = "#dde6ed"

    plot.add_layout(Span(visible=False, dimension="height", line_color="grey",
                         line_dash="dashed", name=f"hoverline_{name}"))
    plot.add_layout(Span(visible=False, dimension="height", line_color="red",
                         name=f"click_line_{name}"))
    for event, handler in (
        ("tap", "handleTap"), ("doubletap", "handleDoubleClick"),
        ("selectiongeometry", "handleRegionBoxSelect"),
    ):
        plot.js_on_event(event, CustomJS(code=f"window.NoiseSurveyApp?.eventHandlers?.{handler}(cb_obj);"))
    plot.js_on_event("mousemove", CustomJS(args={"plot": plot}, code="""
        const {x, y} = cb_obj;
        const inside = x >= plot.x_range.start && x <= plot.x_range.end
            && y >= plot.y_range.start && y <= plot.y_range.end;
        window.NoiseSurveyApp?.eventHandlers?.handleChartHover(
            {geometry: inside ? {x, y} : null}, plot.name);
    """))
    plot.js_on_event("mouseleave", CustomJS(args={"plot": plot}, code="""
        window.NoiseSurveyApp?.eventHandlers?.handleChartHover({geometry: null}, plot.name);
    """))
    return plot


def build_weather_chart(weather, x_range):
    data = weather.samples
    plotted = data.copy()
    for key in ("time", "interval_start"):
        plotted[key] = data[key].astype("int64") / 1_000_000
    gaps = plotted.loc[plotted["interval_start"].gt(plotted["time"].shift())].copy()
    gaps["time"] = gaps["interval_start"]
    gaps[["wind", "gust", "direction", "rain"]] = float("nan")
    line_data = pd.concat([plotted, gaps], ignore_index=True).sort_values("time", kind="stable") if not gaps.empty else plotted
    shared = ColumnDataSource(line_data, name="weather_samples")
    plots = []

    direction = plotted.dropna(subset=["direction"]).copy()
    if not direction.empty:
        direction["compass"] = direction["direction"].map(lambda value: COMPASS[int(value / 22.5 + 0.5) % 16])
        compass = _plot("weather_direction", x_range, height=65, title=f"Weather · {weather.label}",
                        y_range=Range1d(-12, 372), y_axis_label="Wind from")
        compass.title.text_font_size = "12px"
        compass.title.text_color = "#26364b"
        compass.xaxis.visible = False
        compass.yaxis.ticker = FixedTicker(ticks=[0, 90, 180, 270, 360])
        compass.yaxis.major_label_overrides = {0: "N", 90: "E", 180: "S", 270: "W", 360: "N"}
        points = compass.scatter("time", "direction", source=ColumnDataSource(direction), size=4,
                                 color=DIRECTION_COLOR, alpha=0.72, line_color=None)
        compass.add_tools(HoverTool(renderers=[points], tooltips=[
            ("Time (UTC)", "@time{%d %b %H:%M}"), ("Wind from", "@compass (@direction{0.#}°)"),
        ], formatters={"@time": "datetime"}))
        plots.append(compass)

    has_wind = data[["wind", "gust"]].notna().any().any()
    has_rain = data["rain"].notna().any()
    if has_wind or has_rain:
        wind_max = data[["wind", "gust"]].max().max() if has_wind else 0
        rain_max = data["rain"].max() if has_rain else 0
        weather_plot = _plot(
            "weather_wind_rain", x_range, height=115 if plots else 150,
            y_range=Range1d(0, max(1, 1.1 * (wind_max if has_wind else rain_max))),
            y_axis_label="Wind (m/s)" if has_wind else "Rain (mm)",
            title="" if plots else f"Weather · {weather.label}",
        )
        weather_plot.title.text_font_size = "12px"
        weather_plot.yaxis.ticker = BasicTicker(desired_num_ticks=4)
        if has_rain:
            rain_axis = {}
            if has_wind:
                weather_plot.extra_y_ranges["rain"] = Range1d(0, max(1, 1.1 * rain_max))
                weather_plot.add_layout(LinearAxis(
                    y_range_name="rain", axis_label="Rain (mm)", axis_label_text_font_size="10px",
                    axis_label_text_font_style="normal", axis_label_text_color=RAIN_COLOR,
                    major_label_text_font_size="9px", major_label_text_color=RAIN_COLOR,
                    ticker=BasicTicker(desired_num_ticks=4),
                ), "right")
                rain_axis = {"y_range_name": "rain"}
            rain = weather_plot.quad(
                left="interval_start", right="time", bottom=0, top="rain",
                source=ColumnDataSource(plotted.loc[plotted["rain"].gt(0)]),
                fill_color=RAIN_COLOR, line_color=RAIN_COLOR, alpha=0.52,
                legend_label="Rain per interval", **rain_axis,
            )
            weather_plot.add_tools(HoverTool(renderers=[rain], tooltips=[
                ("Interval (UTC)", "@interval_start{%d %b %H:%M} – @time{%H:%M}"),
                ("Rain", "@rain{0.00} mm"),
            ], formatters={"@interval_start": "datetime", "@time": "datetime"}))
        for key, label, color, dash in (
            ("wind", "Mean wind", WIND_COLOR, "solid"),
            ("gust", "Gust", GUST_COLOR, "dashed"),
        ):
            count = data[key].count()
            if count:
                if count == 1:
                    renderer = weather_plot.scatter("time", key, source=shared, size=5,
                                                   color=color, legend_label=label)
                else:
                    renderer = weather_plot.line("time", key, source=shared, line_color=color,
                                                line_dash=dash, line_width=1.5, legend_label=label)
                weather_plot.add_tools(HoverTool(renderers=[renderer], tooltips=[
                    ("Time (UTC)", "@time{%d %b %H:%M}"), (label, f"@{key}{{0.0}} m/s"),
                ], formatters={"@time": "datetime"}))
        legend = weather_plot.legend[0]
        weather_plot.center.remove(legend)
        weather_plot.add_layout(legend, "above")
        legend.orientation = "horizontal"
        legend.location = "top_left"
        legend.label_text_font_size = "9px"
        legend.padding = 0
        legend.margin = 0
        legend.spacing = 10
        legend.border_line_alpha = 0
        plots.append(weather_plot)
    else:
        plots[0].height = 130
        plots[0].xaxis.visible = True

    return column(*plots, name="survey_weather", sizing_mode="stretch_width", margin=(3, 1, 2, 1))
