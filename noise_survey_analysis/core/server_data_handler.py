import logging
from typing import Dict, Optional

import pandas as pd

from noise_survey_analysis.core.config import (
    CHART_SETTINGS,
    LITE_TARGET_POINTS,
    STREAMING_VIEWPOINT_MULTIPLIER,
)
from noise_survey_analysis.core.data_manager import DataManager
from noise_survey_analysis.core.data_processors import GlyphDataProcessor, downsample_dataframe_max

logger = logging.getLogger(__name__)


class ServerDataHandler:
    def __init__(
        self,
        doc,
        app_data: DataManager,
        chart_settings: Optional[Dict] = None,
        lite_target_points: int = LITE_TARGET_POINTS,
        streaming_viewpoint_multiplier: int = STREAMING_VIEWPOINT_MULTIPLIER,
    ) -> None:
        self.doc = doc
        self.app_data = app_data
        self.chart_settings = chart_settings or CHART_SETTINGS
        self.lite_target_points = lite_target_points
        self.streaming_viewpoint_multiplier = streaming_viewpoint_multiplier
        self.processor = GlyphDataProcessor()
        self.selected_parameter = self.chart_settings.get('default_spectral_param', 'LZeq')
        self.position_models = self._collect_position_models()

    def _collect_position_models(self) -> Dict[str, Dict[str, object]]:
        models: Dict[str, Dict[str, object]] = {}
        for position_id in self.app_data.positions():
            models[position_id] = {
                'log_source': self.doc.get_model_by_name(f"source_{position_id}_timeseries_log"),
                'spectrogram_source': self.doc.get_model_by_name(f"source_{position_id}_spectrogram"),
                'timeseries_figure': self.doc.get_model_by_name(f"figure_{position_id}_timeseries"),
                'spectrogram_figure': self.doc.get_model_by_name(f"figure_{position_id}_spectrogram"),
            }
        return models

    def set_selected_parameter(self, param: str) -> None:
        if isinstance(param, str) and param.strip():
            self.selected_parameter = param.strip()

    def handle_range_update(self, start_ms: float, end_ms: float) -> None:
        if not isinstance(start_ms, (int, float)) or not isinstance(end_ms, (int, float)):
            return
        for position_id in self.app_data.positions():
            self._update_position(position_id, start_ms, end_ms)

    def _update_position(self, position_id: str, start_ms: float, end_ms: float) -> None:
        position_data = self.app_data[position_id]
        model_bundle = self.position_models.get(position_id, {})
        if position_data.has_log_totals:
            self._update_log_totals(position_data.log_totals, model_bundle, start_ms, end_ms)
        if position_data.has_log_spectral:
            self._update_log_spectrogram(position_data.log_spectral, model_bundle, start_ms, end_ms)

    def _update_log_totals(self, df: pd.DataFrame, model_bundle: Dict[str, object], start_ms: float, end_ms: float) -> None:
        log_source = model_bundle.get('log_source')
        if log_source is None or df is None or df.empty:
            return
        sliced = self._slice_by_time(df, start_ms, end_ms)
        if sliced.empty:
            return
        target_points = self._calculate_target_points(model_bundle.get('timeseries_figure'))
        downsampled = downsample_dataframe_max(sliced, target_points)
        data = downsampled.copy()
        data.loc[:, 'Datetime'] = pd.to_datetime(data['Datetime']).astype('int64') // 10**6
        log_source.data = data.to_dict(orient='list')

    def _update_log_spectrogram(self, df: pd.DataFrame, model_bundle: Dict[str, object], start_ms: float, end_ms: float) -> None:
        spectrogram_source = model_bundle.get('spectrogram_source')
        if spectrogram_source is None or df is None or df.empty:
            return
        param = self.selected_parameter
        param_columns = [col for col in df.columns if col.startswith(f"{param}_")]
        if not param_columns:
            return
        subset = df[['Datetime', *param_columns]]
        sliced = self._slice_by_time(subset, start_ms, end_ms)
        if sliced.empty:
            return
        target_points = self._calculate_target_points(model_bundle.get('spectrogram_figure'))
        downsampled = downsample_dataframe_max(sliced, target_points)
        prepared = self.processor.prepare_single_spectrogram_data(downsampled, param, self.chart_settings)
        if prepared and prepared.get('initial_glyph_data'):
            spectrogram_source.data = prepared['initial_glyph_data']

    def _slice_by_time(self, df: pd.DataFrame, start_ms: float, end_ms: float) -> pd.DataFrame:
        if df is None or df.empty or 'Datetime' not in df.columns:
            return df
        start, end = sorted([start_ms, end_ms])
        times = pd.to_datetime(df['Datetime'])
        mask = (times >= pd.to_datetime(start, unit='ms')) & (times <= pd.to_datetime(end, unit='ms'))
        return df.loc[mask]

    def _calculate_target_points(self, figure_model) -> int:
        width = getattr(figure_model, 'width', None)
        if not isinstance(width, (int, float)) or width <= 0:
            return self.lite_target_points
        return max(self.lite_target_points, int(width * self.streaming_viewpoint_multiplier))
