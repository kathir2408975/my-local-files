
import plotly.graph_objects as go
import plotly.offline as plot
import plotly.express as px
import pandas as pd
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union, Any

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    Professional GenAI Model Monitoring Report Generator
    
    This class generates comprehensive HTML reports for GenAI model monitoring
    with improved UI, better structure, and enhanced visualizations.
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize the report generator with configuration.
        
        Args:
            config: Optional configuration dictionary to override defaults
        """
        logger.info('Initializing ReportGenerator')
        self.config = config or self._get_default_config()
        self.report_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration for the report generator."""
        return {
            'title': 'GenAI Model Monitoring Report',
            'subtitle': 'LLM-as-a-Judge Assurance Pipeline',
            'description': 'Advanced monitoring pipeline that evaluates GenAI model outputs against predefined criteria, ensuring quality, safety, and alignment with project requirements.',
            'theme': {
                'primary_color': '#2E86AB',
                'secondary_color': '#A23B72', 
                'accent_color': '#F18F01',
                'success_color': '#28a745',
                'danger_color': '#dc3545',
                'warning_color': '#ffc107',
                'info_color': '#17a2b8',
                'light_bg': '#f8f9fa',
                'dark_bg': '#343a40',
                'border_color': '#dee2e6',
                'font_family': "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif"
            },
            'status_colors': {
                'Passed': '#28a745',
                'Failed': '#dc3545', 
                'Skipped': '#6c757d',
                'passed': '#28a745',
                'failed': '#dc3545',
                'skipped': '#6c757d'
            },
            'reverse_metrics': ['Hallucination'],  # Lower is better
            'chart_height': 450
        }

    
    # ==================== UTILITY METHODS ====================
    
    def _find_column(self, df: pd.DataFrame, possible_names: List[str]) -> Optional[str]:
        """
        Find the first matching column name from a list of possibilities.
        
        Args:
            df: DataFrame to search
            possible_names: List of possible column names
            
        Returns:
            First matching column name or None if not found
        """
        try:
            for name in possible_names:
                if name in df.columns:
                    return name
            # Fallback to first column if no match
            return df.columns[0] if len(df.columns) > 0 else None
        except Exception as e:
            logger.error(f"Error finding column: {e}")
            return None
    
    def _safe_numeric_conversion(self, value: Any) -> float:
        """Safely convert value to numeric, returning NaN if conversion fails."""
        try:
            return pd.to_numeric(value, errors='coerce')
        except:
            return float('nan')
    
    def _format_percentage(self, value: float, total: float) -> str:
        """Format a value as percentage of total."""
        if total == 0:
            return "0%"
        return f"{(value/total)*100:.1f}%"
    
    def _truncate_text(self, text: str, max_length: int = 100) -> str:
        """Truncate text to specified length with ellipsis."""
        text = str(text).strip()
        if len(text) <= max_length:
            return text
        return text[:max_length-3] + "..."
    
    # ==================== STATUS CALCULATION ====================
    
    def _calculate_status(self, df: pd.DataFrame, metrics: List[str], thresholds: Dict[str, float]) -> pd.DataFrame:
        """
        Calculate pass/fail status for each metric based on thresholds.
        
        Args:
            df: DataFrame containing metric scores
            metrics: List of metric names
            thresholds: Dictionary mapping metric names to threshold values
            
        Returns:
            DataFrame with added status columns
        """
        try:
            df_copy = df.copy()
            
            for metric in metrics:
                if metric not in df_copy.columns:
                    continue
                    
                status_col = f"{metric}_status"
                reason_col = f"{metric}-reason"
                threshold = thresholds.get(metric)
                
                if threshold is None:
                    df_copy[status_col] = "Unknown"
                    continue
                
                # Check for reason column (for skipped status)
                if reason_col in df_copy.columns:
                    df_copy[status_col] = df_copy.apply(
                        lambda row: self._determine_status_with_reason(
                            row, metric, reason_col, threshold
                        ), axis=1
                    )
                else:
                    df_copy[status_col] = df_copy[metric].apply(
                        lambda x: self._determine_status_simple(x, metric, threshold)
                    )
                    
            return df_copy
            
        except Exception as e:
            logger.error(f"Error calculating status: {e}")
            return df
    
    def _determine_status_with_reason(self, row: pd.Series, metric: str, reason_col: str, threshold: float) -> str:
        """Determine status considering reason column."""
        reason = str(row.get(reason_col, "")).strip().upper()
        if reason == "NA":
            return "Skipped"
        
        score = self._safe_numeric_conversion(row[metric])
        if pd.isna(score):
            return "Failed"
        
        if metric in self.config['reverse_metrics']:
            return "Passed" if score <= threshold else "Failed"
        else:
            return "Passed" if score >= threshold else "Failed"
    
    def _determine_status_simple(self, value: Any, metric: str, threshold: float) -> str:
        """Determine status based only on value and threshold."""
        score = self._safe_numeric_conversion(value)
        if pd.isna(score):
            return "Failed"
        
        if metric in self.config['reverse_metrics']:
            return "Passed" if score <= threshold else "Failed"
        else:
            return "Passed" if score >= threshold else "Failed"

    
    # ==================== CHART GENERATION ====================
    
    def _create_modern_charts(self, summary_df: pd.DataFrame, overall_df: pd.DataFrame, 
                            metrics_df: pd.DataFrame, metrics_col: str, score_col: str, 
                            threshold_col: str) -> Dict[str, str]:
        """
        Create modern, professional charts with improved styling.
        
        Args:
            summary_df: Summary statistics by metric
            overall_df: Overall performance statistics  
            metrics_df: Individual metric details
            metrics_col: Name of metrics column
            score_col: Name of score column
            threshold_col: Name of threshold column
            
        Returns:
            Dictionary of chart HTML strings
        """
        try:
            charts = {}
            theme = self.config['theme']
            
            # 1. METRICS OVERVIEW BAR CHART
            charts['metrics'] = self._create_metrics_bar_chart(summary_df, theme)
            
            # 2. OVERALL PERFORMANCE PIE CHART  
            charts['overall'] = self._create_overall_pie_chart(overall_df, theme)
            
            # 3. SCORE VS THRESHOLD COMPARISON
            charts['comparison'] = self._create_score_comparison_chart(
                metrics_df, metrics_col, score_col, threshold_col, theme
            )
            
            return charts
            
        except Exception as e:
            logger.error(f"Error creating charts: {e}")
            return {}
    
    def _create_metrics_bar_chart(self, summary_df: pd.DataFrame, theme: Dict) -> str:
        """Create metrics overview bar chart."""
        try:
            # Transform data for plotting
            chart_data = []
            metrics_col = self._find_column(summary_df, ['Metrics', 'Metric'])
            
            for _, row in summary_df.iterrows():
                metric = row[metrics_col] if metrics_col else 'Unknown'
                for col in summary_df.columns:
                    if col in ['Metrics', 'Metric', 'Total TCs', 'total']:
                        continue
                    chart_data.append({
                        'Metric': metric, 
                        'Status': col, 
                        'Count': row[col]
                    })
            
            if not chart_data:
                return "<div>No data available for metrics chart</div>"
            
            chart_df = pd.DataFrame(chart_data)
            
            fig = px.bar(
                chart_df, 
                x="Metric", 
                y="Count", 
                color="Status",
                color_discrete_map=self.config['status_colors'],
                barmode="group",
                title="Metrics Performance Overview"
            )
            
            fig.update_layout(
                **self._get_chart_layout(theme),
                xaxis_title="Metrics",
                yaxis_title="Number of Test Cases",
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="center",
                    x=0.5
                )
            )
            
            return plot.plot(fig, output_type='div', include_plotlyjs=False)
            
        except Exception as e:
            logger.error(f"Error creating metrics bar chart: {e}")
            return f"<div>Error creating metrics chart: {e}</div>"
    
    def _create_overall_pie_chart(self, overall_df: pd.DataFrame, theme: Dict) -> str:
        """Create overall performance pie chart."""
        try:
            # Look for columns containing 'passed', 'failed', 'skipped' (case insensitive)
            status_cols = []
            for col in overall_df.columns:
                col_lower = col.lower()
                if any(status in col_lower for status in ['passed', 'failed', 'skipped']):
                    status_cols.append(col)
            
            if not status_cols:
                return "<div>No status data available</div>"
            
            values, labels, colors = [], [], []
            total = 0
            
            for col in status_cols:
                val = overall_df[col].sum()
                total += val
                if val > 0:
                    values.append(val)
                    # Better label formatting - remove "Overall " prefix and clean up
                    label = col.replace('Overall ', '').replace('overall_', '').replace('_', ' ').title()
                    labels.append(f"{label} ({val})")
                    
                    # Determine color based on status type
                    col_lower = col.lower()
                    if 'passed' in col_lower:
                        color_key = 'passed'
                    elif 'failed' in col_lower:
                        color_key = 'failed'
                    elif 'skipped' in col_lower:
                        color_key = 'skipped'
                    else:
                        color_key = 'passed'  # default
                    
                    colors.append(self.config['status_colors'].get(color_key, theme['primary_color']))
            
            if not values:
                return "<div>No data available for overall chart</div>"
            
            fig = px.pie(
                values=values,
                names=labels,
                title="Overall Performance Distribution",
                hole=0.4,
                color_discrete_sequence=colors
            )
            
            fig.update_traces(
                textposition='inside',
                textinfo='label+percent',
                textfont_size=12,
                hovertemplate="<b>%{label}</b><br>Percentage: %{percent}<extra></extra>"
            )
            
            fig.update_layout(
                **self._get_chart_layout(theme),
                showlegend=True,
                legend=dict(
                    orientation="h",
                    yanchor="bottom", 
                    y=-0.2,
                    xanchor="center",
                    x=0.5
                ),
                annotations=[{
                    "text": f"Total<br>{total}",
                    "x": 0.5, "y": 0.5,
                    "font_size": 16,
                    "showarrow": False
                }]
            )
            
            return plot.plot(fig, output_type='div', include_plotlyjs=False)
            
        except Exception as e:
            logger.error(f"Error creating overall pie chart: {e}")
            return f"<div>Error creating overall chart: {e}</div>"
    
    def _create_score_comparison_chart(self, metrics_df: pd.DataFrame, metrics_col: str,
                                     score_col: str, threshold_col: str, theme: Dict) -> str:
        """Create score vs threshold comparison chart."""
        try:
            metrics = metrics_df[metrics_col].tolist()
            scores = [self._safe_numeric_conversion(x) for x in metrics_df[score_col].tolist()]
            thresholds = [self._safe_numeric_conversion(x) for x in metrics_df[threshold_col].tolist()]
            
            # Determine colors based on pass/fail
            bar_colors = []
            for score, threshold, metric in zip(scores, thresholds, metrics):
                if pd.isna(score) or pd.isna(threshold):
                    bar_colors.append(theme['border_color'])
                    continue
                    
                if metric in self.config['reverse_metrics']:
                    color = self.config['status_colors']['passed'] if score <= threshold else self.config['status_colors']['failed']
                else:
                    color = self.config['status_colors']['passed'] if score >= threshold else self.config['status_colors']['failed']
                bar_colors.append(color)
            
            fig = go.Figure()
            
            # Add score bars
            fig.add_trace(go.Bar(
                x=metrics,
                y=scores,
                name='Actual Score',
                marker_color=bar_colors,
                hovertemplate="<b>%{x}</b><br>Score: %{y:.3f}<extra></extra>",
                opacity=0.8
            ))
            
            # Add threshold line
            fig.add_trace(go.Scatter(
                x=metrics,
                y=thresholds,
                mode='lines+markers',
                name='Threshold',
                line=dict(color=theme['accent_color'], width=3, dash='dash'),
                marker=dict(size=8, color=theme['accent_color']),
                hovertemplate="<b>%{x}</b><br>Threshold: %{y:.3f}<extra></extra>"
            ))
            
            fig.update_layout(
                **self._get_chart_layout(theme),
                title="Score vs Threshold Comparison",
                xaxis_title="Metrics",
                yaxis_title="Score",
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="center", 
                    x=0.5
                )
            )
            
            # Update yaxis range separately to avoid conflict
            fig.update_yaxes(range=[0, 1.1])
            
            return plot.plot(fig, output_type='div', include_plotlyjs=False)
            
        except Exception as e:
            logger.error(f"Error creating score comparison chart: {e}")
            return f"<div>Error creating comparison chart: {e}</div>"
        
    def _get_chart_layout(self, theme: Dict) -> Dict:
        """Get common chart layout configuration."""
        return {
            'font': {'family': theme['font_family'], 'size': 12},
            'plot_bgcolor': 'rgba(0,0,0,0)',
            'paper_bgcolor': 'rgba(0,0,0,0)',
            'height': self.config['chart_height'],
            'margin': dict(l=60, r=60, t=80, b=100),
            'xaxis': {
                'showgrid': True,
                'gridcolor': theme['border_color'],
                'tickangle': -45,
                'tickfont': {'size': 10}
            },
            'yaxis': {
                'showgrid': True, 
                'gridcolor': theme['border_color'],
                'tickfont': {'size': 10}
            }
        }

    
    # ==================== DATA PREPARATION ====================
    
    def _prepare_modal_data(self, df: pd.DataFrame, metrics: List[str], thresholds: Dict[str, float]) -> Dict:
        """
        Prepare structured data for modal popups with comprehensive field handling.
        
        Args:
            df: DataFrame with test case details
            metrics: List of metric names
            thresholds: Dictionary of threshold values
            
        Returns:
            Dictionary indexed by row index containing modal data
        """
        try:
            modal_data = {}
            
            for idx, row in df.iterrows():
                # Find context column flexibly
                context_text = self._get_context_text(row)
                
                # Base modal data structure
                modal_data[idx] = {
                    'question': self._clean_text(row.get('question', 'N/A')),
                    'response': self._clean_text(row.get('response', 'N/A')),
                    'context': context_text,
                    'ground_truth_response': self._clean_text(row.get('ground_truth_response', 'N/A')),
                    'timestamp': self.report_timestamp,
                    'metrics': {}
                }
                
                # Add optional fields if they exist
                self._add_optional_fields(modal_data[idx], row, df.columns)
                
                # Add metrics data
                self._add_metrics_data(modal_data[idx], row, metrics, thresholds)
                
            return modal_data
            
        except Exception as e:
            logger.error(f"Error preparing modal data: {e}")
            return {}
    
    def _get_context_text(self, row: pd.Series) -> str:
        """Extract context text from various possible column names."""
        if 'context' in row.index:
            return self._clean_text(row['context'])
        
        # Search for context-like columns
        context_cols = [col for col in row.index if 'context' in col.lower()]
        if context_cols:
            return self._clean_text(row[context_cols[0]])
        
        return 'N/A'
    
    def _clean_text(self, text: Any) -> str:
        """Clean and format text for display."""
        if pd.isna(text) or text is None:
            return 'N/A'
        
        text = str(text).strip()
        if not text or text.lower() in ['nan', 'none', '']:
            return 'N/A'
        
        return text
    
    def _add_optional_fields(self, modal_item: Dict, row: pd.Series, columns: List[str]) -> None:
        """Add optional fields to modal data if they exist in the DataFrame."""
        optional_field_map = {
            'citations': ['citations', 'citation'],
            'meta_data': ['meta_data', 'admin_meta_data'],
            'project_context': ['project_context'],
            'selected_pills': ['persona', 'chat_options'],
            'execution_time': ['execution_time', 'response_time'],
            'model_version': ['model_version', 'model'],
            'confidence_score': ['confidence', 'confidence_score']
        }
        
        for target_field, possible_cols in optional_field_map.items():
            if target_field == 'meta_data':
                # Special handling for metadata
                meta_dict = {}
                for col in possible_cols:
                    if col in columns:
                        meta_dict[col] = self._clean_text(row.get(col, ''))
                if meta_dict:
                    modal_item['meta_data'] = json.dumps(meta_dict, indent=2)
                    
            elif target_field == 'selected_pills':
                # Special handling for pills/persona
                pills_dict = {}
                for col in possible_cols:
                    if col in columns:
                        pills_dict[col] = self._clean_text(row.get(col, ''))
                if pills_dict:
                    modal_item['selected_pills'] = json.dumps(pills_dict, indent=2)
                    
            else:
                # Standard field handling
                for col in possible_cols:
                    if col in columns:
                        modal_item[target_field] = self._clean_text(row.get(col, 'N/A'))
                        break
                else:
                    modal_item[target_field] = 'N/A'
    
    def _add_metrics_data(self, modal_item: Dict, row: pd.Series, metrics: List[str], thresholds: Dict) -> None:
        """Add metrics data to modal item."""
        for metric in metrics:
            metric_data = {
                'score': self._clean_text(row.get(metric, 'N/A')),
                'threshold': str(thresholds.get(metric, 'N/A')),
                'status': self._clean_text(row.get(f"{metric}_status", 'Unknown')),
                'additional_fields': {}
            }
            
            # Find additional metric-related columns
            for col in row.index:
                if col.startswith(metric) and col != metric and not col.endswith('_status'):
                    field_name = col.replace(f"{metric}_", "").replace(f"{metric}-", "")
                    field_value = self._clean_text(row.get(col, ''))
                    if field_value != 'N/A':
                        metric_data['additional_fields'][field_name] = field_value
            
            modal_item['metrics'][metric] = metric_data

    
    def _generate_modern_modal(self) -> str:
        """Generate modern modal HTML structure."""
        return f"""
        <div id="detailModal" class="modal">
            <div class="modal-content">
                <div class="modal-header">
                    <div>
                        <h3 class="modal-title" id="modalTitle">Metric Details</h3>
                        <p class="modal-subtitle" id="modalSubtitle">Threshold: N/A</p>
                    </div>
                    <button class="modal-close" onclick="closeModal()">×</button>
                </div>
                <div class="modal-body">
                    <div class="modal-left">
                        <div class="modal-section">
                            <h4>Question</h4>
                            <p id="modalQuestion">N/A</p>
                        </div>
                        
                        <div class="collapsible-section">
                            <div class="collapsible-header" onclick="toggleCollapsible('response')">
                                <h4>Response</h4>
                                <span class="toggle-icon" id="responseIcon">▼</span>
                            </div>
                            <div class="collapsible-content collapsed" id="responseContent">
                                <p id="modalResponse">N/A</p>
                            </div>
                        </div>
                        
                        <div class="modal-section">
                            <h4>Citations</h4>
                            <p id="modalCitations">N/A</p>
                        </div>
                        
                        <div class="collapsible-section">
                            <div class="collapsible-header" onclick="toggleCollapsible('context')">
                                <h4>Context</h4>
                                <span class="toggle-icon" id="contextIcon">▼</span>
                            </div>
                            <div class="collapsible-content collapsed" id="contextContent">
                                <p id="modalContext">N/A</p>
                            </div>
                        </div>
                        
                        <div class="collapsible-section">
                            <div class="collapsible-header" onclick="toggleCollapsible('metadata')">
                                <h4>Documents & Metadata</h4>
                                <span class="toggle-icon" id="metadataIcon">▼</span>
                            </div>
                            <div class="collapsible-content collapsed" id="metadataContent">
                                <p id="modalMetadata">N/A</p>
                            </div>
                        </div>
                        
                        <div class="collapsible-section">
                            <div class="collapsible-header" onclick="toggleCollapsible('projectContext')">
                                <h4>Project Context</h4>
                                <span class="toggle-icon" id="projectContextIcon">▼</span>
                            </div>
                            <div class="collapsible-content collapsed" id="projectContextContent">
                                <p id="modalProjectContext">N/A</p>
                            </div>
                        </div>
                        
                        <div class="modal-section">
                            <h4>Selected Configuration</h4>
                            <p id="modalConfiguration">N/A</p>
                        </div>
                        
                        <div class="modal-section">
                            <h4>Ground Truth Response</h4>
                            <p id="modalGroundTruth">N/A</p>
                        </div>
                    </div>
                    
                    <div class="modal-right">
                        <div class="score-visualization">
                            <h4>Score Analysis</h4>
                            <div id="scorePieChart"></div>
                        </div>
                        
                        <div class="modal-section">
                            <h4>Evaluation Reason</h4>
                            <p id="modalReason">N/A</p>
                        </div>
                        
                        <div id="additionalMetricFields"></div>
                    </div>
                </div>
            </div>
        </div>
        """

    
    # ==================== UI COMPONENTS ====================
    
    def _get_modern_css(self) -> str:
        """
        Generate modern, professional CSS with improved design and responsiveness.
        
        Returns:
            CSS string with modern styling
        """
        theme = self.config['theme']
        status_colors = self.config['status_colors']
        
        return f"""
        /* =============== GLOBAL STYLES =============== */
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        
        body {{
            font-family: {theme['font_family']};
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            min-height: 100vh;
            margin: 0;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        
        /* =============== HEADER STYLES =============== */
        .report-header {{
            background: linear-gradient(135deg, {theme['primary_color']} 0%, {theme['secondary_color']} 100%);
            color: white;
            padding: 40px;
            text-align: center;
            position: relative;
            overflow: hidden;
        }}
        
        .report-header::before {{
            content: '';
            position: absolute;
            top: -50%;
            left: -50%;
            width: 200%;
            height: 200%;
            background: repeating-linear-gradient(
                0deg,
                transparent,
                transparent 2px,
                rgba(255,255,255,0.03) 2px,
                rgba(255,255,255,0.03) 4px
            );
            animation: shimmer 20s linear infinite;
        }}
        
        @keyframes shimmer {{
            0% {{ transform: translateX(-100%); }}
            100% {{ transform: translateX(100%); }}
        }}
        
        .report-title {{
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
            position: relative;
            z-index: 1;
        }}
        
        .report-subtitle {{
            font-size: 1.4rem;
            font-weight: 300;
            margin-bottom: 15px;
            opacity: 0.9;
            position: relative;
            z-index: 1;
        }}
        
        .report-description {{
            font-size: 1rem;
            max-width: 800px;
            margin: 0 auto;
            opacity: 0.85;
            line-height: 1.6;
            position: relative;
            z-index: 1;
        }}
        
        .report-timestamp {{
            position: absolute;
            top: 20px;
            right: 20px;
            background: rgba(255,255,255,0.2);
            padding: 8px 15px;
            border-radius: 20px;
            font-size: 0.9rem;
            z-index: 2;
        }}
        
        /* =============== TAB NAVIGATION =============== */
        .tab-navigation {{
            background: {theme['light_bg']};
            border-bottom: 3px solid {theme['primary_color']};
            display: flex;
            justify-content: center;
            padding: 0;
            position: sticky;
            top: 0;
            z-index: 100;
        }}
        
        .tab-button {{
            background: none;
            border: none;
            padding: 20px 30px;
            font-size: 1.1rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.3s ease;
            position: relative;
            color: #666;
        }}
        
        .tab-button:hover {{
            background: rgba(46, 134, 171, 0.1);
            color: {theme['primary_color']};
        }}
        
        .tab-button.active {{
            background: {theme['primary_color']};
            color: white;
            box-shadow: inset 0 -3px 0 {theme['accent_color']};
        }}
        
        .tab-button.active::after {{
            content: '';
            position: absolute;
            bottom: -3px;
            left: 0;
            right: 0;
            height: 3px;
            background: {theme['accent_color']};
        }}
        
        /* =============== TAB CONTENT =============== */
        .tab-content {{
            display: none;
            padding: 30px;
            animation: fadeIn 0.3s ease-in;
        }}
        
        .tab-content.active {{
            display: block;
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        /* =============== CARD COMPONENTS =============== */
        .card {{
            background: white;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
            margin-bottom: 25px;
            overflow: hidden;
            transition: all 0.3s ease;
            border: 1px solid {theme['border_color']};
        }}
        
        .card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 8px 30px rgba(0,0,0,0.12);
        }}
        
        .card-header {{
            background: linear-gradient(135deg, {theme['primary_color']} 0%, {theme['secondary_color']} 100%);
            color: white;
            padding: 20px;
            font-weight: 600;
            font-size: 1.2rem;
            position: relative;
        }}
        
        .card-content {{
            padding: 20px;
        }}
        
        /* =============== CHARTS GRID =============== */
        .charts-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
            gap: 25px;
            margin-bottom: 30px;
        }}
        
        .chart-card {{
            background: white;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
            overflow: hidden;
            transition: all 0.3s ease;
        }}
        
        .chart-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 8px 30px rgba(0,0,0,0.12);
        }}
        
        .chart-card.full-width {{
            grid-column: 1 / -1;
        }}
        
        /* =============== TABLES =============== */
        .table-container {{
            background: white;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
            overflow: hidden;
            margin-bottom: 25px;
        }}
        
        .modern-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.95rem;
        }}
        
        .modern-table th {{
            background: linear-gradient(135deg, {theme['primary_color']} 0%, {theme['secondary_color']} 100%);
            color: white;
            padding: 15px 12px;
            text-align: left;
            font-weight: 600;
            border: none;
            position: sticky;
            top: 0;
            z-index: 10;
        }}
        
        .modern-table td {{
            padding: 12px;
            border-bottom: 1px solid {theme['border_color']};
            vertical-align: top;
        }}
        
        .modern-table tr:hover {{
            background: rgba(46, 134, 171, 0.04);
        }}
        
        .modern-table tr:nth-child(even) {{
            background: rgba(0,0,0,0.02);
        }}
        
        .modern-table tr:nth-child(even):hover {{
            background: rgba(46, 134, 171, 0.04);
        }}
        
        /* =============== STATUS INDICATORS =============== */
        .status-cell {{
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 600;
            text-align: center;
            min-width: 80px;
            display: inline-block;
            cursor: pointer;
            transition: all 0.2s ease;
        }}
        
        .status-cell:hover {{
            transform: scale(1.05);
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        }}
        
        .status-passed {{
            background: {status_colors['passed']};
            color: white;
        }}
        
        .status-failed {{
            background: {status_colors['failed']};
            color: white;
        }}
        
        .status-skipped {{
            background: {status_colors['skipped']};
            color: white;
        }}
        
        .metric-score {{
            font-weight: 600;
            font-size: 1.1rem;
        }}
        
        .below-threshold {{
            background: linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%);
            color: {status_colors['failed']};
            font-weight: bold;
            border-left: 4px solid {status_colors['failed']};
        }}
        
        .equal-threshold {{
            background: linear-gradient(135deg, #fff8e1 0%, #ffecb3 100%);
            color: #e65100;
            font-weight: bold;
            border-left: 4px solid {theme['warning_color']};
        }}
        
        /* =============== PAGINATION =============== */
        .pagination-container {{
            background: {theme['light_bg']};
            border-top: 1px solid {theme['border_color']};
            padding: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 15px;
        }}
        
        .pagination-controls {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        .page-btn {{
            padding: 10px 15px;
            border: 1px solid {theme['border_color']};
            background: white;
            cursor: pointer;
            border-radius: 6px;
            font-size: 14px;
            transition: all 0.2s ease;
            min-width: 40px;
            text-align: center;
        }}
        
        .page-btn:hover:not(:disabled) {{
            background: {theme['primary_color']};
            color: white;
            border-color: {theme['primary_color']};
        }}
        
        .page-btn.active {{
            background: {theme['primary_color']};
            color: white;
            border-color: {theme['primary_color']};
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        
        .page-btn:disabled {{
            background: {theme['light_bg']};
            color: #999;
            cursor: not-allowed;
            border-color: {theme['border_color']};
        }}
        
        .page-info {{
            font-size: 0.9rem;
            color: #666;
            font-weight: 500;
        }}
        
        .rows-selector {{
            padding: 8px 12px;
            border: 1px solid {theme['border_color']};
            border-radius: 6px;
            background: white;
            font-size: 14px;
        }}
        
        /* =============== MODAL STYLES =============== */
        .modal {{
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.6);
            backdrop-filter: blur(5px);
        }}
        
        .modal-content {{
            background: white;
            margin: 2% auto;
            border-radius: 15px;
            display: flex;
            flex-direction: column;
            width: 95%;
            max-width: 1400px;
            max-height: 90vh;
            overflow: hidden;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            animation: modalSlideIn 0.3s ease-out;
        }}
        
        @keyframes modalSlideIn {{
            from {{
                opacity: 0;
                transform: translateY(-50px) scale(0.9);
            }}
            to {{
                opacity: 1;
                transform: translateY(0) scale(1);
            }}
        }}
        
        .modal-header {{
            background: linear-gradient(135deg, {theme['primary_color']} 0%, {theme['secondary_color']} 100%);
            color: white;
            padding: 25px;
            position: relative;
        }}
        
        .modal-title {{
            font-size: 1.5rem;
            font-weight: 600;
            margin: 0;
        }}
        
        .modal-subtitle {{
            font-size: 1rem;
            opacity: 0.9;
            margin: 5px 0 0;
        }}
        
        .modal-close {{
            position: absolute;
            top: 20px;
            right: 25px;
            background: rgba(255,255,255,0.2);
            border: none;
            color: white;
            font-size: 24px;
            font-weight: bold;
            cursor: pointer;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s ease;
        }}
        
        .modal-close:hover {{
            background: rgba(255,255,255,0.3);
            transform: scale(1.1);
        }}
        
        .modal-body {{
            display: flex;
            flex: 1;
            overflow: hidden;
        }}
        
        .modal-left {{
            flex: 2;
            padding: 25px;
            overflow-y: auto;
            border-right: 1px solid {theme['border_color']};
        }}
        
        .modal-right {{
            flex: 1;
            padding: 25px;
            overflow-y: auto;
            background: {theme['light_bg']};
        }}
        
        .modal-section {{
            background: white;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            border-left: 4px solid {theme['accent_color']};
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }}
        
        .modal-section h4 {{
            color: {theme['primary_color']};
            margin-bottom: 10px;
            font-size: 1.1rem;
            font-weight: 600;
        }}
        
        .modal-section p {{
            line-height: 1.6;
            color: #555;
        }}
        
        .collapsible-section {{
            background: white;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            overflow: hidden;
        }}
        
        .collapsible-header {{
            background: linear-gradient(135deg, {theme['light_bg']} 0%, rgba(46, 134, 171, 0.1) 100%);
            padding: 15px 20px;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-left: 4px solid {theme['accent_color']};
            transition: all 0.2s ease;
        }}
        
        .collapsible-header:hover {{
            background: linear-gradient(135deg, rgba(46, 134, 171, 0.1) 0%, rgba(46, 134, 171, 0.2) 100%);
        }}
        
        .collapsible-content {{
            padding: 20px;
            max-height: 200px;
            overflow-y: auto;
            transition: all 0.3s ease;
            border-left: 4px solid {theme['accent_color']};
        }}
        
        .collapsible-content.collapsed {{
            max-height: 0;
            padding: 0 20px;
            overflow: hidden;
        }}
        
        .toggle-icon {{
            font-size: 1.2rem;
            transition: transform 0.3s ease;
            color: {theme['primary_color']};
        }}
        
        .toggle-icon.expanded {{
            transform: rotate(180deg);
        }}
        
        .score-visualization {{
            text-align: center;
            background: white;
            border-radius: 8px;
            padding: 15px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            max-width: 100%;
            overflow: hidden;
        }}
        
        .score-visualization h4 {{
            margin-bottom: 10px;
            margin-top: 0;
        }}
        
        #scorePieChart {{
            margin: 0 auto;
            display: flex;
            justify-content: center;
            align-items: center;
            max-width: 100%;
            max-height: 200px;
            overflow: hidden;
        }}
        
        /* =============== RESPONSIVE DESIGN =============== */
        @media (max-width: 1200px) {{
            .charts-grid {{
                grid-template-columns: 1fr;
            }}
            
            .modal-body {{
                flex-direction: column;
            }}
            
            .modal-left, .modal-right {{
                flex: none;
            }}
            
            .modal-left {{
                border-right: none;
                border-bottom: 1px solid {theme['border_color']};
            }}
        }}
        
        @media (max-width: 768px) {{
            .container {{
                margin: 10px;
                border-radius: 10px;
            }}
            
            .report-header {{
                padding: 30px 20px;
            }}
            
            .report-title {{
                font-size: 2rem;
            }}
            
            .report-subtitle {{
                font-size: 1.2rem;
            }}
            
            .tab-content {{
                padding: 20px;
            }}
            
            .pagination-container {{
                flex-direction: column;
                align-items: stretch;
            }}
            
            .pagination-controls {{
                justify-content: center;
            }}
            
            .modal-content {{
                width: 98%;
                max-height: 95vh;
            }}
            
            .modal-left, .modal-right {{
                padding: 20px;
            }}
        }}
        
        /* =============== LOADING STATES =============== */
        .loading {{
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(46, 134, 171, 0.3);
            border-radius: 50%;
            border-top-color: {theme['primary_color']};
            animation: spin 1s ease-in-out infinite;
        }}
        
        @keyframes spin {{
            to {{ transform: rotate(360deg); }}
        }}
        
        .fade-in {{
            animation: fadeIn 0.5s ease-in;
        }}
        
        /* =============== UTILITY CLASSES =============== */
        .text-center {{ text-align: center; }}
        .text-right {{ text-align: right; }}
        .mb-0 {{ margin-bottom: 0; }}
        .mb-1 {{ margin-bottom: 0.5rem; }}
        .mb-2 {{ margin-bottom: 1rem; }}
        .mb-3 {{ margin-bottom: 1.5rem; }}
        .mt-0 {{ margin-top: 0; }}
        .mt-1 {{ margin-top: 0.5rem; }}
        .mt-2 {{ margin-top: 1rem; }}
        .mt-3 {{ margin-top: 1.5rem; }}
        
        .p-0 {{ padding: 0; }}
        .p-1 {{ padding: 0.5rem; }}
        .p-2 {{ padding: 1rem; }}
        .p-3 {{ padding: 1.5rem; }}
        
        .font-weight-bold {{ font-weight: 700; }}
        .font-weight-normal {{ font-weight: 400; }}
        .font-size-sm {{ font-size: 0.875rem; }}
        .font-size-lg {{ font-size: 1.125rem; }}
        
        .text-primary {{ color: {theme['primary_color']}; }}
        .text-secondary {{ color: {theme['secondary_color']}; }}
        .text-success {{ color: {status_colors['passed']}; }}
        .text-danger {{ color: {status_colors['failed']}; }}
        .text-warning {{ color: {theme['warning_color']}; }}
        .text-muted {{ color: #666; }}
        """


    
    # ==================== TABLE GENERATION ====================
    
    def _generate_metrics_summary_table(self, df: pd.DataFrame) -> str:
        """
        Generate modern metrics summary table with improved formatting.
        
        Args:
            df: DataFrame containing metrics summary data
            
        Returns:
            HTML string for the metrics table
        """
        try:
            if df.empty:
                return "<div class='text-center p-3'>No metrics data available</div>"
            
            # Find important columns
            threshold_col = self._find_column(df, ['Threshold_Value', 'Threshold'])
            score_col = self._find_column(df, ['aggregate_score', 'score', 'Score'])
            metrics_col = self._find_column(df, ['Metrics', 'Metric'])
            
            html = ['<div class="table-container">']
            html.append('<table class="modern-table">')
            
            # Table header
            html.append('<thead><tr>')
            for col in df.columns:
                display_name = col.replace('_', ' ').title()
                html.append(f'<th>{display_name}</th>')
            html.append('</tr></thead>')
            
            # Table body
            html.append('<tbody>')
            for _, row in df.iterrows():
                html.append('<tr>')
                for col in df.columns:
                    value = row[col]
                    
                    # Format numeric values
                    if isinstance(value, (int, float)) and not pd.isna(value):
                        if col in [threshold_col, score_col]:
                            value = f'{value:.3f}'
                        else:
                            value = f'{value:.2f}' if value != int(value) else str(int(value))
                    
                    # Handle text formatting
                    if pd.isna(value) or value is None:
                        value = 'N/A'
                    else:
                        value = str(value).replace('\n', '<br>').replace('\r', '')
                    
                    # Add cell styling for scores vs thresholds
                    cell_class = ''
                    if col == score_col and threshold_col and score_col:
                        cell_class = self._get_score_cell_class(
                            row, score_col, threshold_col, metrics_col
                        )
                    
                    html.append(f'<td class="{cell_class} metric-score">{value}</td>')
                html.append('</tr>')
            
            html.append('</tbody>')
            html.append('</table>')
            html.append('</div>')
            
            return '\n'.join(html)
            
        except Exception as e:
            logger.error(f"Error generating metrics table: {e}")
            return f"<div class='alert alert-error'>Error generating table: {e}</div>"
    
    def _get_score_cell_class(self, row: pd.Series, score_col: str, 
                            threshold_col: str, metrics_col: str) -> str:
        """Determine CSS class for score cell based on threshold comparison."""
        try:
            if not all([score_col, threshold_col, metrics_col]):
                return ''
            
            score = self._safe_numeric_conversion(row.get(score_col))
            threshold = self._safe_numeric_conversion(row.get(threshold_col))
            metric = row.get(metrics_col, '')
            
            if pd.isna(score) or pd.isna(threshold):
                return ''
            
            # Check threshold performance
            if metric in self.config['reverse_metrics']:
                # Lower is better
                if score > threshold:
                    return 'below-threshold'
            else:
                # Higher is better  
                if score < threshold:
                    return 'below-threshold'
            
            # Check if exactly at threshold
            if abs(score - threshold) < 0.001:
                return 'equal-threshold'
            
            return ''
            
        except Exception as e:
            logger.error(f"Error determining score cell class: {e}")
            return ''
    
    def _generate_interactive_details_table(self, df: pd.DataFrame, metrics: List[str]) -> str:
        """
        Generate modern interactive details table with pagination and modal integration.
        
        Args:
            df: DataFrame containing detailed test case data
            metrics: List of metric names for the table columns
            
        Returns:
            HTML string for the interactive table with JavaScript
        """
        try:
            if df.empty:
                return "<div class='text-center p-3'>No details data available</div>"
            
            html = []
            
            # Start table container
            html.append('<div class="table-container">')
            html.append('<table class="modern-table">')
            html.append('<thead><tr>')
            html.append('<th style="min-width: 200px;">Question</th>')
            html.append('<th style="min-width: 200px;">Response</th>')
            
            # Add metric headers
            for metric in metrics:
                display_name = metric.replace('_', ' ').title()
                html.append(f'<th class="text-center" style="min-width: 120px;">{display_name}</th>')
            
            html.append('</tr></thead>')
            html.append('<tbody id="tableBody"></tbody>')
            html.append('</table>')
            html.append('</div>')
            
            # Add pagination container
            html.append(self._generate_pagination_controls())
            
            # Generate JavaScript for table functionality
            html.append(self._generate_table_javascript(df, metrics))
            
            return '\n'.join(html)
            
        except Exception as e:
            logger.error(f"Error generating details table: {e}")
            return f"<div class='alert alert-error'>Error generating details table: {e}</div>"

    
    def _generate_pagination_controls(self) -> str:
        """Generate pagination controls HTML."""
        return f"""
        <div class="pagination-container">
            <div class="pagination-controls">
                <select id="rowsPerPage" class="rows-selector" onchange="changeRowsPerPage()">
                    <option value="10">10 rows/page</option>
                    <option value="25">25 rows/page</option>
                    <option value="50">50 rows/page</option>
                    <option value="100">100 rows/page</option>
                </select>
            </div>
            <div class="pagination-controls" id="paginationButtons"></div>
            <div class="page-info">
                <span id="pageInfo">Page 1 of 1</span>
            </div>
        </div>
        """
    
    def _generate_table_javascript(self, df: pd.DataFrame, metrics: List[str]) -> str:
        """
        Generate JavaScript for interactive table functionality.
        
        Args:
            df: DataFrame with table data
            metrics: List of metric names
            
        Returns:
            JavaScript code as HTML script tag
        """
        try:
            # Prepare table data as JSON
            table_data = []
            
            for idx, row in df.iterrows():
                # Prepare question and response (truncated for table display)
                question_short = self._truncate_text(str(row.get('question', 'N/A')), 50)
                response_short = self._truncate_text(str(row.get('response', 'N/A')), 50)
                
                # Prepare metric data
                metric_cells = {}
                for metric in metrics:
                    status_col = f"{metric}_status"
                    status = row.get(status_col, 'Unknown')
                    score = row.get(metric, 'N/A')
                    
                    # Format score
                    if pd.notna(score) and isinstance(score, (int, float)):
                        formatted_score = f'{score:.3f}'
                    else:
                        formatted_score = str(score) if score != 'N/A' else 'N/A'
                    
                    # Determine CSS class
                    css_class = 'status-unknown'
                    if str(status).lower() == 'passed':
                        css_class = 'status-passed'
                    elif str(status).lower() == 'failed':
                        css_class = 'status-failed'
                    elif str(status).lower() == 'skipped':
                        css_class = 'status-skipped'
                    
                    metric_cells[metric] = {
                        'value': formatted_score,
                        'status': status,
                        'class': css_class,
                        'clickable': formatted_score != 'N/A'
                    }
                
                table_data.append({
                    'index': int(idx),
                    'question': question_short,
                    'response': response_short,
                    'metrics': metric_cells
                })
            
            # Convert to JSON for JavaScript
            table_data_json = json.dumps(table_data)
            metrics_json = json.dumps(metrics)
            
            return f"""
            <script>
            let currentPage = 1;
            let rowsPerPage = 10;
            let totalRows = 0;
            let allTableData = {table_data_json};
            let allMetrics = {metrics_json};
            
            function initializeTable() {{
                totalRows = allTableData.length;
                displayPage();
            }}
            
            function displayPage() {{
                const startIdx = (currentPage - 1) * rowsPerPage;
                const endIdx = Math.min(startIdx + rowsPerPage, totalRows);
                const tbody = document.getElementById('tableBody');
                
                if (!tbody) return;
                
                let html = '';
                
                for (let i = startIdx; i < endIdx; i++) {{
                    const rowData = allTableData[i];
                    html += '<tr>';
                    
                    // Question and Response columns
                    html += `<td>${{rowData.question}}</td>`;
                    html += `<td>${{rowData.response}}</td>`;
                    
                    // Metric columns
                    allMetrics.forEach(metric => {{
                        const metricData = rowData.metrics[metric];
                        if (metricData.clickable) {{
                            html += `<td class="text-center">
                                <span class="status-cell ${{metricData.class}}" 
                                      onclick="openModal(${{rowData.index}}, '${{metric}}')"
                                      title="Click for details">
                                    ${{metricData.value}}
                                </span>
                            </td>`;
                        }} else {{
                            html += `<td class="text-center">
                                <span class="status-cell status-skipped">N/A</span>
                            </td>`;
                        }}
                    }});
                    
                    html += '</tr>';
                }}
                
                tbody.innerHTML = html;
                updatePaginationInfo();
            }}
            
            function updatePaginationInfo() {{
                const totalPages = Math.ceil(totalRows / rowsPerPage);
                const pageInfoEl = document.getElementById('pageInfo');
                if (pageInfoEl) {{
                    pageInfoEl.textContent = `Page ${{currentPage}} of ${{totalPages}} (Showing ${{Math.min(rowsPerPage, totalRows - (currentPage - 1) * rowsPerPage)}} of ${{totalRows}} records)`;
                }}
                renderPaginationButtons(totalPages);
            }}
            
            function renderPaginationButtons(totalPages) {{
                const container = document.getElementById('paginationButtons');
                if (!container) return;
                
                let html = '';
                const maxVisible = 5;
                
                // First and Previous buttons
                html += `<button class="page-btn" onclick="goToPage(1)" ${{currentPage === 1 ? 'disabled' : ''}}>First</button>`;
                html += `<button class="page-btn" onclick="previousPage()" ${{currentPage === 1 ? 'disabled' : ''}}>Prev</button>`;
                
                // Page number buttons
                let startPage = Math.max(1, currentPage - Math.floor(maxVisible / 2));
                let endPage = Math.min(totalPages, startPage + maxVisible - 1);
                
                if (endPage - startPage + 1 < maxVisible) {{
                    startPage = Math.max(1, endPage - maxVisible + 1);
                }}
                
                // Add ellipsis and first page if needed
                if (startPage > 1) {{
                    html += `<button class="page-btn" onclick="goToPage(1)">1</button>`;
                    if (startPage > 2) {{
                        html += `<span class="page-btn disabled">...</span>`;
                    }}
                }}
                
                // Page number buttons
                for (let i = startPage; i <= endPage; i++) {{
                    html += `<button class="page-btn ${{i === currentPage ? 'active' : ''}}" onclick="goToPage(${{i}})">${{i}}</button>`;
                }}
                
                // Add ellipsis and last page if needed
                if (endPage < totalPages) {{
                    if (endPage < totalPages - 1) {{
                        html += `<span class="page-btn disabled">...</span>`;
                    }}
                    html += `<button class="page-btn" onclick="goToPage(${{totalPages}})">${{totalPages}}</button>`;
                }}
                
                // Next and Last buttons
                html += `<button class="page-btn" onclick="nextPage()" ${{currentPage === totalPages ? 'disabled' : ''}}>Next</button>`;
                html += `<button class="page-btn" onclick="goToPage(${{totalPages}})" ${{currentPage === totalPages ? 'disabled' : ''}}>Last</button>`;
                
                container.innerHTML = html;
            }}
            
            function goToPage(page) {{
                const totalPages = Math.ceil(totalRows / rowsPerPage);
                if (page >= 1 && page <= totalPages) {{
                    currentPage = page;
                    displayPage();
                }}
            }}
            
            function nextPage() {{
                const totalPages = Math.ceil(totalRows / rowsPerPage);
                if (currentPage < totalPages) {{
                    currentPage++;
                    displayPage();
                }}
            }}
            
            function previousPage() {{
                if (currentPage > 1) {{
                    currentPage--;
                    displayPage();
                }}
            }}
            
            function changeRowsPerPage() {{
                const select = document.getElementById('rowsPerPage');
                if (select) {{
                    rowsPerPage = parseInt(select.value);
                    currentPage = 1;
                    displayPage();
                }}
            }}
            
            // Initialize table when DOM is loaded
            document.addEventListener('DOMContentLoaded', initializeTable);
            </script>
            """
            
        except Exception as e:
            logger.error(f"Error generating table JavaScript: {e}")
            return f"<script>console.error('Error generating table JavaScript: {e}');</script>"


    
    # ==================== HTML GENERATION ====================
    
    def _generate_modern_html(self, metrics_df: pd.DataFrame, details_df: pd.DataFrame, 
                            all_metrics: List[str], charts: Dict[str, str], modal_data: Dict) -> str:
        """
        Generate modern HTML report with improved structure and styling.
        
        Args:
            metrics_df: DataFrame with metrics summary
            details_df: DataFrame with detailed test case data
            all_metrics: List of metric names
            charts: Dictionary containing chart HTML
            modal_data: Dictionary containing modal data
            
        Returns:
            Complete HTML document string
        """
        try:
            # Build the complete HTML document
            html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.config['title']}</title>
    <style>{self._get_modern_css()}</style>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
</head>
<body>
    <div class="container">
        <div class="report-header">
            <div class="report-timestamp">Generated: {self.report_timestamp}</div>
            <h1 class="report-title">{self.config['title']}</h1>
            <h2 class="report-subtitle">{self.config['subtitle']}</h2>
            <p class="report-description">{self.config['description']}</p>
        </div>
        
        <nav class="tab-navigation">
            <button class="tab-button active" onclick="showTab('metrics', event)">
                📊 Metrics Summary
            </button>
            <button class="tab-button" onclick="showTab('analytics', event)">
                📈 Analytics Dashboard
            </button>
            <button class="tab-button" onclick="showTab('details', event)">
                🔍 Detailed Results
            </button>
        </nav>
        
        <main>
            <div id="metrics" class="tab-content active">
                <div class="card">
                    <div class="card-content">
                        {self._generate_metrics_summary_table(metrics_df)}
                    </div>
                </div>
            </div>
            
            <div id="analytics" class="tab-content">
                <div class="charts-grid">
                    <div class="chart-card">
                        <div class="card-header">
                            <h3>🎯 Overall Performance Distribution</h3>
                        </div>
                        <div class="card-content">
                            {charts.get('overall', '<div>No overall chart data available</div>')}
                        </div>
                    </div>
                    
                    <div class="chart-card">
                        <div class="card-header">
                            <h3>📊 Metrics Performance Comparison</h3>
                        </div>
                        <div class="card-content">
                            {charts.get('comparison', '<div>No comparison chart data available</div>')}
                        </div>
                    </div>
                    
                    <div class="chart-card full-width">
                        <div class="card-header">
                            <h3>📋 Metrics Overview by Status</h3>
                        </div>
                        <div class="card-content">
                            {charts.get('metrics', '<div>No metrics chart data available</div>')}
                        </div>
                    </div>
                </div>
            </div>
            
            <div id="details" class="tab-content">
                    <div class="card-content p-0">
                        {self._generate_interactive_details_table(details_df, all_metrics)}
                </div>
            </div>
        </main>
    </div>
    
    {self._generate_modern_modal()}
    
    <script>
        // Global data
        const modalData = {json.dumps(modal_data, default=str)};
        const config = {json.dumps(self.config, default=str)};
        
        // Tab functionality
        function showTab(tabName, event) {{
            // Remove active class from all tabs and buttons
            document.querySelectorAll('.tab-content').forEach(tab => {{
                tab.classList.remove('active');
            }});
            document.querySelectorAll('.tab-button').forEach(btn => {{
                btn.classList.remove('active');
            }});
            
            // Add active class to selected tab and button
            const selectedTab = document.getElementById(tabName);
            if (selectedTab) {{
                selectedTab.classList.add('active');
            }}
            if (event && event.target) {{
                event.target.classList.add('active');
            }}
            
            // Force Plotly charts to resize when switching to analytics tab
            if (tabName === 'analytics') {{
                setTimeout(() => {{
                    document.querySelectorAll('#analytics .plotly-graph-div').forEach(div => {{
                        if (window.Plotly) {{
                            try {{
                                window.Plotly.Plots.resize(div);
                            }} catch (e) {{
                                console.warn('Error resizing chart:', e);
                            }}
                        }}
                    }});
                }}, 100);
            }}
        }}
        
        // Modal functionality
        function closeModal() {{
            const modal = document.getElementById('detailModal');
            if (modal) {{
                modal.style.display = 'none';
            }}
        }}
        
        function toggleCollapsible(sectionId) {{
            const content = document.getElementById(sectionId + 'Content');
            const icon = document.getElementById(sectionId + 'Icon');
            
            if (content && icon) {{
                if (content.classList.contains('collapsed')) {{
                    content.classList.remove('collapsed');
                    icon.classList.add('expanded');
                    icon.textContent = '▲';
                }} else {{
                    content.classList.add('collapsed');
                    icon.classList.remove('expanded');
                    icon.textContent = '▼';
                }}
            }}
        }}
        
        function openModal(rowIndex, metricName) {{
            const modal = document.getElementById('detailModal');
            if (!modal || !modalData[rowIndex]) {{
                console.error('Modal or data not found');
                return;
            }}
            
            const data = modalData[rowIndex];
            const metricData = data.metrics[metricName] || {{}};
            
            // Reset modal scroll positions
            const modalLeft = modal.querySelector('.modal-left');
            const modalRight = modal.querySelector('.modal-right');
            if (modalLeft) modalLeft.scrollTop = 0;
            if (modalRight) modalRight.scrollTop = 0;
            
            // Reset collapsible sections
            ['response', 'context', 'metadata', 'projectContext'].forEach(sectionId => {{
                const content = document.getElementById(sectionId + 'Content');
                const icon = document.getElementById(sectionId + 'Icon');
                if (content && icon) {{
                    content.classList.add('collapsed');
                    icon.classList.remove('expanded');
                    icon.textContent = '▼';
                }}
            }});
            
            // Update modal content
            const updateElement = (id, content) => {{
                const element = document.getElementById(id);
                if (element) {{
                    element.textContent = content || 'N/A';
                }}
            }};
            
            updateElement('modalTitle', `${{metricName.replace(/_/g, ' ').toUpperCase()}} Details`);
            updateElement('modalSubtitle', `Threshold: ${{metricData.threshold || 'N/A'}}`);
            updateElement('modalQuestion', data.question);
            updateElement('modalResponse', data.response);
            updateElement('modalContext', data.context);
            updateElement('modalCitations', data.citations);
            updateElement('modalMetadata', data.meta_data);
            updateElement('modalProjectContext', data.project_context);
            updateElement('modalConfiguration', data.selected_pills);
            updateElement('modalGroundTruth', data.ground_truth_response);
            updateElement('modalReason', metricData.additional_fields?.reason || 'No reason provided');
            
            // Handle additional metric fields
            const additionalFieldsDiv = document.getElementById('additionalMetricFields');
            if (additionalFieldsDiv && metricData.additional_fields) {{
                additionalFieldsDiv.innerHTML = '';
                const processedFields = new Set(['reason', 'status']);
                
                Object.keys(metricData.additional_fields).forEach(fieldName => {{
                    if (!processedFields.has(fieldName)) {{
                        const fieldValue = metricData.additional_fields[fieldName];
                        if (fieldValue && fieldValue !== 'nan' && fieldValue !== 'N/A') {{
                            const fieldDiv = document.createElement('div');
                            fieldDiv.className = 'modal-section';
                            fieldDiv.innerHTML = `
                                <h4>${{fieldName.charAt(0).toUpperCase() + fieldName.slice(1).replace(/_/g, ' ')}}</h4>
                                <p>${{fieldValue}}</p>
                            `;
                            additionalFieldsDiv.appendChild(fieldDiv);
                        }}
                    }}
                }});
            }}
            
            // Create score visualization
            const scoreElement = document.getElementById('scorePieChart');
            if (scoreElement && metricData.score && metricData.threshold) {{
                createScorePieChart(
                    parseFloat(metricData.score), 
                    parseFloat(metricData.threshold), 
                    metricName
                );
            }}
            
            // Show modal
            modal.style.display = 'block';
        }}
        
        function createScorePieChart(score, threshold, metric) {{
            if (isNaN(score) || isNaN(threshold)) return;
            
            const remaining = Math.max(0, 1 - score);
            const isReverse = config.reverse_metrics?.includes(metric) || false;
            const isPass = isReverse ? score <= threshold : score >= threshold;
            
            const statusColors = config.status_colors || config.colors || {{}};
            const passColor = statusColors.passed || statusColors.Passed || '#28a745';
            const failColor = statusColors.failed || statusColors.Failed || '#dc3545';
            
            const data = [{{
                values: [score, remaining],
                labels: ['Score', 'Remaining'],
                type: 'pie',
                hole: 0.4,
                marker: {{
                    colors: [isPass ? passColor : failColor, '#f0f0f0']
                }},
                textinfo: 'none',
                hovertemplate: '<b>%{{label}}</b><br>Value: %{{value:.3f}}<br>Percentage: %{{percent}}<extra></extra>'
            }}];
            
            const layout = {{
                showlegend: false,
                margin: {{ t: 20, b: 20, l: 20, r: 20 }},
                height: 160,
                width: 160,
                autosize: false,
                annotations: [{{
                    text: score.toFixed(3) + '<br>' + (isPass ? 'PASS' : 'FAIL'),
                    x: 0.5,
                    y: 0.5,
                    font: {{ size: 14, color: isPass ? passColor : failColor, weight: 'bold' }},
                    showarrow: false,
                    align: 'center'
                }}],
                plot_bgcolor: 'rgba(0,0,0,0)',
                paper_bgcolor: 'rgba(0,0,0,0)'
            }};
            
            try {{
                Plotly.newPlot('scorePieChart', data, layout, {{ displayModeBar: false, responsive: true }});
            }} catch (e) {{
                console.error('Error creating score chart:', e);
            }}
        }}
        
        // Global click handler for modal
        window.addEventListener('click', function(event) {{
            const modal = document.getElementById('detailModal');
            if (event.target === modal) {{
                closeModal();
            }}
        }});
        
        // Keyboard handler for modal
        document.addEventListener('keydown', function(event) {{
            if (event.key === 'Escape') {{
                closeModal();
            }}
        }});
        
        // Initialize on page load
        document.addEventListener('DOMContentLoaded', function() {{
            console.log('Report loaded successfully');
            // Initialize any additional functionality here
        }});
    </script>
</body>
</html>"""
            
            return html_content
            
        except Exception as e:
            logger.error(f"Error generating HTML: {e}")
            return f"""<!DOCTYPE html>
<html>
<head><title>Report Generation Error</title></head>
<body>
    <div style="padding: 20px; text-align: center;">
        <h1 style="color: #dc3545;">Error Generating Report</h1>
        <p>An error occurred while generating the report: {e}</p>
        <p>Please check the data format and try again.</p>
    </div>
</body>
</html>"""

    
    # ==================== MAIN REPORT GENERATION ====================
    
    def generate_report(self, metrics_df: pd.DataFrame, details_df: pd.DataFrame, 
                       summary_df: pd.DataFrame, overall_df: pd.DataFrame) -> str:
        """
        Generate a comprehensive monitoring report from the provided DataFrames.
        
        Args:
            metrics_df: DataFrame containing metrics summary and thresholds
            details_df: DataFrame containing detailed test case results  
            summary_df: DataFrame containing metrics-wise pass/fail summary
            overall_df: DataFrame containing overall performance statistics
            
        Returns:
            HTML string containing the complete report
        """
        try:
            logger.info("Starting report generation")
            
            # Validate input data
            if any(df.empty for df in [metrics_df, details_df, summary_df, overall_df]):
                logger.warning("One or more input DataFrames are empty")
                return self._generate_error_report("One or more input DataFrames are empty")
            
            # Find column names flexibly
            metrics_col = self._find_column(metrics_df, ['Metrics', 'Metric', 'metric'])
            threshold_col = self._find_column(metrics_df, ['Threshold_Value', 'Threshold', 'threshold'])
            score_col = self._find_column(metrics_df, ['aggregate_score', 'score', 'Score'])
            
            if not all([metrics_col, threshold_col, score_col]):
                logger.warning("Required columns not found in metrics DataFrame")
                return self._generate_error_report("Required columns not found in metrics DataFrame")
            
            # Extract metrics list and thresholds
            all_metrics = metrics_df[metrics_col].tolist()
            thresholds = dict(zip(metrics_df[metrics_col], metrics_df[threshold_col]))
            
            logger.info(f"Processing {len(all_metrics)} metrics: {all_metrics}")
            
            # Calculate pass/fail status for each metric
            details_df = self._calculate_status(details_df, all_metrics, thresholds)
            
            # Generate charts
            charts = self._create_modern_charts(
                summary_df, overall_df, metrics_df, metrics_col, score_col, threshold_col
            )
            
            # Prepare modal data
            modal_data = self._prepare_modal_data(details_df, all_metrics, thresholds)
            
            # Generate final HTML
            html_content = self._generate_modern_html(
                metrics_df, details_df, all_metrics, charts, modal_data
            )
            
            logger.info("Report generation completed successfully")
            return html_content
            
        except Exception as e:
            logger.error(f"Error in report generation: {e}")
            return self._generate_error_report(f"Error in report generation: {e}")
    
    def _generate_error_report(self, error_message: str) -> str:
        """Generate a simple error report HTML."""
        return f"""<!DOCTYPE html>
<html>
<head>
    <title>Report Generation Error</title>
    <style>
        body {{ font-family: Arial, sans-serif; padding: 40px; text-align: center; }}
        .error {{ color: #dc3545; margin: 20px 0; }}
        .suggestion {{ color: #6c757d; margin: 20px 0; }}
    </style>
</head>
<body>
    <h1>Report Generation Error</h1>
    <div class="error">{error_message}</div>
    <div class="suggestion">
        Please check that your data contains the required columns:<br>
        • Metrics DataFrame: 'Metrics'/'Metric', 'Threshold'/'Threshold_Value', 'Score'/'aggregate_score'<br>
        • Details DataFrame: 'question', 'response', metric score columns<br>
        • Summary DataFrame: metrics pass/fail counts<br>
        • Overall DataFrame: overall pass/fail counts
    </div>
</body>
</html>"""

def demo_report_generation():
    """
    Demonstration of how to use the ReportGenerator class with sample data.
    """
    import pandas as pd
    
    try:
        input_file_path = '/content/Metrics_template.xlsx'
        metrics_df= pd.read_excel(input_file_path, sheet_name='Metrics Interpretability')
        details_df= pd.read_excel(input_file_path, sheet_name='Test Data')
        summary_df= pd.read_excel(input_file_path, sheet_name='Metrics_wise Pass-Fail')
        overall_df=pd.read_excel(input_file_path, sheet_name='Overall Summary')
        
        # Generate the report
        report_generator = ReportGenerator()
        html_content = report_generator.generate_report(
            metrics_df, details_df, summary_df, overall_df
        )
        
        # Save the demo report
        try:
          file_path = "/content/report.html"
          with open(file_path, "w") as f:
              f.write(html_content)
          print(f"HTML content saved to {file_path}")
        except Exception as e:
          logger.info(f"Exception in line {sys.exc_info()[-1].tb_lineno}: {e}")
        
        print(f"✅ Demo report generated successfully!")
        print("\n🎯 Key Features:")
        print("• Modern responsive design with professional styling")
        print("• Interactive charts with Plotly integration")
        print("• Paginated data tables with search functionality")
        print("• Detailed modal popups for drill-down analysis")
        print("• Mobile-friendly responsive layout")
        print("• Professional color scheme and typography")
        
        return "Report generated successfully"
        
    except Exception as e:
        print(f"❌ Error generating demo report: {e}")
        return None


if __name__ == "__main__":
    demo_report_generation()