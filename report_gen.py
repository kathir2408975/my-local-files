
import plotly.graph_objects as go
import plotly.offline as plot
import plotly.express as px
import pandas as pd
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union, Any
from flask import Flask, request, Response
import tempfile
import os
import pandas as pd
import plotly.express as px
import plotly.offline as plot
import re
import unicodedata

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
        self.metric_details_excel_path = Path(__file__).resolve().parent / "Detailed_Log.xlsx"
        
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

    def _load_rca_data(self) -> pd.DataFrame:
        try:
            df = pd.read_excel(self.metric_details_excel_path, sheet_name="RCA")
            df["Query"] = df["Query"].astype(str).str.strip()
            df["Looping_agent"] = df["Looping_agent"].astype(str)
            return df
        except Exception as e:
            logger.error(f"Error loading RCA sheet: {e}")
            return pd.DataFrame()
 
    def _normalize_query_match(self, text: str) -> str:
        if not text:
            return ""
    
        text = str(text)
    
        # unify unicode quotes etc
        text = unicodedata.normalize("NFKD", text)
    
        # lowercase
        text = text.lower()
    
        # remove punctuation
        text = re.sub(r"[^\w\s]", "", text)
    
        # collapse spaces
        text = re.sub(r"\s+", " ", text).strip()
    
        return text

    def _normalize_text(self, text: Any) -> str:
        """Universal text normalization for comparisons."""
        if text is None:
            return ""
        text = str(text)
        text = unicodedata.normalize("NFKD", text)
        text = text.lower()
        text = re.sub(r"[^\w\s]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text
 
 
    def _text_equal(self, a: Any, b: Any) -> bool:
        """Compare two text fields ignoring case, punctuation, spacing."""
        return self._normalize_text(a) == self._normalize_text(b)

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

            base_dir = Path(__file__).resolve().parent

            charts['coverage'] = self._create_test_coverage_sunburst(excel_path=base_dir / "Metrics_template.xlsx", sheet_name='Test data coverage')
            charts['aggregated'] = self._create_aggregated_chart(metrics_df, theme)
            charts['disaggregated'] = self._create_disaggregated_table(
                Path(__file__).resolve().parent / "Metrics_template.xlsx"
            )            
            return charts
            
        except Exception as e:
            logger.error(f"Error creating charts: {e}")
            return {}
    
    def _create_metrics_bar_chart(self, summary_df: pd.DataFrame, theme: Dict) -> str:
        try:
            metrics_col = self._find_column(summary_df, ['Metrics', 'Metric'])
            passed_col = self._find_column(summary_df, ["Passed"])
            failed_col = self._find_column(summary_df, ["Failed"])
    
            metrics = summary_df[metrics_col].astype(str).tolist()
            failed = summary_df[failed_col].fillna(0).tolist()
            passed = summary_df[passed_col].fillna(0).tolist()  
            fig = go.Figure()
    
            fig.add_bar(
                x=metrics, 
                y=failed, 
                name='Failed', 
                marker_color=self.config['status_colors']['Failed']
            )
            fig.add_bar(
                x=metrics, 
                y=passed, 
                name='Passed', 
                marker_color=self.config['status_colors']['Passed']
            )
    
            fig.update_layout(
                barmode='group',
                title='Metrics Performance Overview',
                xaxis_title='Metrics',
                yaxis_title='Number of Test Cases',
                bargap=0.25,   
                bargroupgap=0.05,  
                width=len(metrics) * 140,  
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="center",
                    x=0.5
                ),         
                **self._get_chart_layout(theme)
            )
    
            return plot.plot(fig, output_type='div', include_plotlyjs=False)
    
        except Exception as e:
            logger.error(f"Error creating metrics bar chart: {e}")
            return f"<div>Error creating metrics chart: {e}</div>"

    def _create_overall_pie_chart(self, overall_df: pd.DataFrame, theme: Dict) -> str:
        try:
            # Force numeric extraction
            passed = int(overall_df[[c for c in overall_df.columns if 'passed' in c.lower()][0]].sum())
            failed = int(overall_df[[c for c in overall_df.columns if 'failed' in c.lower()][0]].sum())
                
            labels = []
            values = []
            colors = []
    
            if passed > 0:
                labels.append(f"Passed ({passed})")
                values.append(passed)
                colors.append(self.config['status_colors']['passed'])
    
            if failed > 0:
                labels.append(f"Failed ({failed})")
                values.append(failed)
                colors.append(self.config['status_colors']['failed'])
    
            total = sum(values)
    
            fig = go.Figure(
                data=[go.Pie(
                    labels=labels,
                    values=values,
                    hole=0.4,
                    marker=dict(colors=colors),
                    textinfo="label+percent",
                    hoverinfo="label+percent+value"
                )]
            )
    
            fig.update_layout(
                title="Overall Performance Distribution",
                **self._get_chart_layout(theme),
                annotations=[dict(
                    text=f"Total<br>{total}",
                    x=0.5, y=0.5,
                    font_size=16,
                    showarrow=False
                )]
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
                bargap=0.25,          
                bargroupgap=0.05,    
                width=len(metrics) * 140,
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
 
    def _create_test_coverage_sunburst(self, excel_path: str, sheet_name: str) -> str:
        """
        Create Test Coverage Sunburst chart
        - Topic % = percentRoot
        - Sub-topic % = percentParent
        - Shows Count + Percentage EXACTLY like existing report.html
        """
        try:
            # ===============================
            # READ EXCEL
            # ===============================
            df = pd.read_excel(excel_path, sheet_name=sheet_name)
    
            df["topic"] = df["topic"].astype(str).str.strip().str.title().str.upper()
            df["sub_topic"] = df["sub_topic"].astype(str).str.strip().str.title()
            df["query"] = df["query"].astype(str)
    
            overall_count = len(df)
    
            # ===============================
            # TOPIC COUNTS
            # ===============================
            topic_df = (
                df.groupby("topic")
                .size()
                .reset_index(name="topic_count")
            )
    
            topic_df["topic_percentage"] = (
                topic_df["topic_count"] / overall_count * 100
            ).round(2)
    
            # ===============================
            # SUB-TOPIC COUNTS
            # ===============================
            subtopic_df = (
                df.groupby(["topic", "sub_topic"])
                .size()
                .reset_index(name="subtopic_count")
            )
    
            subtopic_df = subtopic_df.merge(
                topic_df, on="topic", how="left"
            )

            # ===============================
            # ATTACH QUERIES PER SUB-TOPIC
            # ===============================
            query_map = (
                df.groupby(["topic", "sub_topic"])["query"]
                .apply(lambda x: "<br>".join(x.astype(str)))
                .reset_index(name="queries")
            )
            
            subtopic_df = subtopic_df.merge(
                query_map,
                on=["topic", "sub_topic"],
                how="left"
            )
    
            subtopic_df["subtopic_percentage"] = (
                subtopic_df["subtopic_count"] /
                subtopic_df["topic_count"] * 100
            ).round(2)
    
            # ===============================
            # SUNBURST
            # ===============================
            fig = px.sunburst(
                subtopic_df,
                path=["topic", "sub_topic"],
                values="subtopic_count",
                color="topic",
                custom_data=[
                    "topic_percentage",
                    "subtopic_percentage",
                    "queries"
                ],
                title="Test Coverage - Topic & Sub-topic Distribution"
            )
    
            # ===============================
            # CONDITIONAL TEXT DISPLAY
            # ===============================
            fig.update_traces(
                texttemplate=(
                    "<b>%{label}</b><br>"
                    "Count: %{value}<br>"
                    "%{percentParent:.0%}"
                ),
                hovertemplate=(
                    "<b>%{label}</b><br>"
                    "Count: %{value}<br>"
                    "%{percentParent:.2%}"
                    "<extra></extra>"
                )
            )
    
            # ===============================
            # FIX LABELS USING LEVEL LOGIC
            # ===============================
            fig.update_traces(
                texttemplate=(
                    "<b>%{label}</b><br>"
                    "Count: %{value}"
                ),
                selector=dict(level=0)
            )

            fig.update_traces(
                texttemplate=(
                    "<b>%{label}</b><br>"
                    "Count: %{value}<br>"
                    "%{percentRoot:.2%}"
                ),
                selector=dict(level=1)
            )
    
            fig.update_traces(
                texttemplate=(
                    "<b>%{label}</b><br>"
                    "Count: %{value}<br>"
                    "%{percentParent:.2%}"
                ),
                selector=dict(level=2)
            )
    
            fig.update_layout(
                margin=dict(t=60, l=20, r=20, b=20)
            )
    
            chart_div = plot.plot(
                fig,
                output_type="div",
                include_plotlyjs="cdn",
            )
            
            click_js = """
            <script>
            (function(){
                var plots = document.querySelectorAll('.plotly-graph-div');
                var plot = plots[plots.length - 1];
            
                if(!plot) return;
            
                // create query container if not exists
                var containerId = "subtopic-query-panel";
                var container = document.getElementById(containerId);
            
                if(!container){
                    container = document.createElement("div");
                    container.id = containerId;
                    container.style.marginTop = "20px";
                    container.style.padding = "12px";
                    container.style.border = "1px solid #ddd";
                    container.style.borderRadius = "6px";
                    container.style.background = "#fafafa";
                    plot.parentNode.appendChild(container);
                }
            
                plot.on('plotly_click', function(data){
                    if(!data || !data.points || !data.points.length) return;
            
                    var point = data.points[0];
            
                    // sub-topic = has parent
                    if(point.parent && point.customdata && point.customdata.length >= 3){
                        var queries = point.customdata[2] || "";
            
                        container.innerHTML =
                            "<h4 style='margin-bottom:8px'>Queries for " + point.label + "</h4>" +
                            queries;
            
                        return false; // stop drilldown
                    }
                });
            })();
            </script>
            """
            return chart_div + click_js
    
        except Exception as e:
            logger.error(f"Error creating test coverage sunburst: {e}")
            return "<div class='text-center p-3'><b>Error loading test coverage</b></div>"

    def _create_run_comparison_chart(self, prev_df: pd.DataFrame, curr_df: pd.DataFrame, theme: Dict) -> str:
        try:
            if prev_df.empty or curr_df.empty:
                return "<div class='text-center p-3'><b>No data available</b></div>"
    
            # helper to find an existing column from candidate names (no fallback to first column)
            def find_existing(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
                for c in candidates:
                    if c in df.columns:
                        return c
                return None
    
            metric_col_prev = find_existing(prev_df, ["Metric", "Metrics", "metric"])
            score_col_prev = find_existing(prev_df, ["Score", "aggregate_score", "score"])
    
            metric_col_curr = find_existing(curr_df, ["Metric", "Metrics", "metric"])
            score_col_curr = find_existing(curr_df, ["Score", "aggregate_score", "score"])
    
            # If any required column is missing, show friendly message
            if not all([metric_col_prev, score_col_prev, metric_col_curr, score_col_curr]):
                return "<div class='text-center p-3'><b>No data available</b></div>"
    
            prev_df = prev_df[[metric_col_prev, score_col_prev]].rename(
                columns={metric_col_prev: "Metric", score_col_prev: "Previous"}
            )
            curr_df = curr_df[[metric_col_curr, score_col_curr]].rename(
                columns={metric_col_curr: "Metric", score_col_curr: "Current"}
            )
    
            merged = pd.merge(prev_df, curr_df, on="Metric", how="inner")
    
            # If merge resulted in no common metrics, show friendly message
            if merged.empty:
                return "<div class='text-center p-3'><b>No data available</b></div>"
    
            fig = go.Figure()
    
            fig.add_bar(
                x=merged["Metric"],
                y=pd.to_numeric(merged["Previous"], errors="coerce"),
                name="Previous Run",
                marker_color=theme["secondary_color"]
            )
    
            fig.add_bar(
                x=merged["Metric"],
                y=pd.to_numeric(merged["Current"], errors="coerce"),
                name="Current Run",
                marker_color=theme["primary_color"]
            )
    
            fig.update_layout(
                barmode="group",
                title="Run Comparison (Previous vs Current)",
                xaxis_title="Metrics",
                yaxis_title="Score",
                **self._get_chart_layout(theme)
            )
    
            return plot.plot(fig, output_type="div", include_plotlyjs=False)
    
        except Exception as e:
            logger.error(f"Run comparison error: {e}")
            return "<div class='text-center p-3'><b>No data available</b></div>"

    def _create_aggregated_chart(self, metrics_df: pd.DataFrame, theme: Dict) -> str:
        try:
            df = metrics_df.copy()

            avg_scores = pd.to_numeric(df['aggregate_score'], errors="coerce").tolist()
            metrics = df['Metrics'].astype(str).tolist()
    
            fig = go.Figure()
    
            fig.add_bar(
                x=metrics,
                y=avg_scores,
                name="Average Score",
                marker_color=theme["primary_color"]
            )
    
            fig.update_layout(
                xaxis_title="Metrics",
                yaxis_title="Score",
                legend=dict(
                    orientation="h",
                    y=1.02,
                    x=0.5,
                    xanchor="center"
                ),
                **self._get_chart_layout(theme)
            )
    
            return plot.plot(
                fig,
                output_type="div",
                include_plotlyjs=False
            )
    
        except Exception as e:
            logger.error(f"Error creating aggregated chart: {e}")
            return f"<div>Error creating aggregated chart: {e}</div>"
        
    def _create_disaggregated_table(self, excel_path: Path) -> str:
        import json
        import pandas as pd
    
        # ===============================
        # READ EXCEL
        # ===============================
        df = pd.read_excel(
            excel_path,
            sheet_name="Disaggregated View",
            header=None
        )

        agg_scores = {}
 
        for col in range(2, len(df.columns)):
            metric = str(df.iloc[0, col]).strip()
            val = df.iloc[1, col]
        
            if metric and metric.lower() != "nan":
                try:
                    agg_scores[metric] = float(val)
                except Exception:
                    agg_scores[metric] = None
    
        parsed = []
        i = 0
    
        # ===============================
        # PARSE EXCEL STRUCTURE
        # ===============================
        while i < len(df):
            cell = str(df.iloc[i, 2]).strip().lower()  # Column C
    
            # Detect "Topic" marker row
            if cell == "topic":
                topic = str(df.iloc[i + 1, 2]).strip()
                sub_topic = str(df.iloc[i + 1, 3]).strip()
    
                records_row = df.iloc[i + 1]   # Total
                pass_row = df.iloc[i + 2]      # Passed
                fail_row = df.iloc[i + 3]      # Failed  
                    
                metrics_data = {}
    
                # Metrics start from column E (index 4)
                for col in range(4, len(df.columns)):
                    metric_name = str(df.iloc[i, col]).strip()
                    if not metric_name or metric_name.lower() == "nan":
                        continue
    
                    try:
                        total_m = int(str(records_row[col]).split()[0])
                        passed_m = int(str(pass_row[col]).split()[0])
                        failed_m = int(str(fail_row[col]).split()[0])                   
                    except Exception:
                        continue
    
                    metrics_data[metric_name] = {
                        "total": total_m,
                        "passed": passed_m,
                        "failed": failed_m,
                        "aggregate_score": agg_scores.get(metric_name)
                    }
    
                parsed.append({
                    "topic": topic,
                    "sub_topic": sub_topic,
                    "metrics": metrics_data
                })
    
                # Skip to next block
                i += 5
            else:
                i += 1
    
        # ===============================
        # HTML + JS
        # ===============================
        return f"""
        <div class="card">
            <div class="card-header">
                <h3>🔍 Disaggregated Analysis</h3>
            </div>
        
            <div class="card-content">
                <label>Topic</label><br>
                <select id="topicSelect"></select>
                <br><br>
                <label>Sub-topic</label><br>
                <div id="subTopicWrapper" class="multi-select">
                    <div id="selectedSubTopics" class="chips"></div>
                    <input id="subTopicInput" placeholder="Select sub-topics" readonly/>
                    <div id="subTopicDropdown" class="dropdown"></div>
                </div>
                <br><br>
                <div id="disaggChart"></div>
            </div>
        </div>
    
        <script>
            const DISAGG_DATA = {json.dumps(parsed)};
        </script>
            """

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

            # Defensive loading of metric details workbook (may be missing in some environments)
            metric_sheets = {}
            try:
                if self.metric_details_excel_path.exists():
                    xls = pd.ExcelFile(self.metric_details_excel_path)
                    for sheet in xls.sheet_names:
                        try:
                            metric_sheets[sheet] = pd.read_excel(xls, sheet_name=sheet)
                        except Exception:
                            # skip unreadable sheets
                            continue
                else:
                    logger.warning(f"Metric details file not found: {self.metric_details_excel_path}")
            except Exception as e:
                logger.warning(f"Unable to read metric details excel: {e}")
                metric_sheets = {}

            # Create case-insensitive mapping from normalized sheet name -> original sheet name
            normalized_sheet_map = {str(s).strip().lower(): s for s in metric_sheets.keys()}

            for idx, row in df.iterrows():
                modal_data[idx] = {
                    'query': self._clean_text(row.get('Query', 'N/A')),
                    'response': self._clean_text(row.get('Response', 'N/A')),
                    'timestamp': self.report_timestamp,
                    'metrics': {}
                }

                # Ensure metric_fields contains an entry for each metric (keeps JS stable)
                modal_data[idx]["metric_fields"] = {}

                # Map sheet rows to metric names (case-insensitive)
                for metric in metrics:
                    norm_metric = str(metric).strip().lower()
                    if norm_metric in normalized_sheet_map:
                        sheet_name = normalized_sheet_map[norm_metric]
                        metric_df = metric_sheets.get(sheet_name)
                        if isinstance(metric_df, pd.DataFrame) and idx < len(metric_df):
                            query_col = self._find_column(metric_df, ['Query', 'query', 'Question'])
                            # Normalized query from details dataframe
                            details_query = self._normalize_text(row.get('Query', ''))
                            found_entry = {}
 
                            if query_col and query_col in metric_df.columns:
                                # Normalize metric sheet query values and compare
                                # Use exact match after stripping; also try replacing newline variations
                                def normalize_q(x):
                                    return str(x).strip().replace('\r\n', '\n').replace('\r', '\n')
 
                                normalized_target = details_query
                                # mask where normalized values equal
                                mask = metric_df[query_col].apply(lambda x: self._normalize_text(x) == normalized_target)
                                matched = metric_df[mask]
 
                                if not matched.empty:
                                    # If single match, return a dict; if multiple, return list of dicts
                                    if len(matched) == 1:
                                        found_entry = matched.iloc[0].replace({pd.NA: None}).to_dict()
                                    else:
                                        found_entry = [
                                            r.replace({pd.NA: None}).to_dict()
                                            for _, r in matched.iterrows()
                                        ]
                                else:
                                    # No exact match — try a looser comparison (strip and collapse whitespace)
                                    mask2 = metric_df[query_col].apply(lambda x: self._text_equal(x, details_query))
                                    matched2 = metric_df[mask2]
                                    if not matched2.empty:
                                        if len(matched2) == 1:
                                            found_entry = matched2.iloc[0].replace({pd.NA: None}).to_dict()
                                        else:
                                            found_entry = [
                                                r.replace({pd.NA: None}).to_dict()
                                                for _, r in matched2.iterrows()
                                            ]
                                    else:
                                        found_entry = {}
                            else:
                                # No Query column found in metric sheet — keep empty dict to avoid JS errors
                                found_entry = {}
 
                            modal_data[idx]["metric_fields"][metric] = found_entry
                        else:
                            modal_data[idx]["metric_fields"][metric] = {}
                    else:
                        # Leave empty dict if no matching sheet - avoids JS key errors
                        modal_data[idx]["metric_fields"][metric] = {}

                # Add metrics data (scores / statuses / additional fields)
                self._add_metrics_data(modal_data[idx], row, metrics, thresholds)
            
            return modal_data

        except Exception as e:
            logger.error(f"Error preparing modal data: {e}")
            return {}
    
    def _clean_text(self, text: Any) -> str:
        """Clean and format text for display."""
        if pd.isna(text) or text is None:
            return 'N/A'
        
        text = str(text).strip()
        if not text or text.lower() in ['nan', 'none', '']:
            return 'N/A'

        text = text.replace('\\n', '\n')

        text = text.replace('\n', '<br>')
        
        return text
    
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

                       <!-- Metric fields container: each Excel column will be rendered here as its own .modal-section -->
                        <div id="metricSheetFieldsContainer">
                            <div id="tracebackFields">N/A</div>
                            <div id="metricSheetFields">N/A</div>
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

        .multi-select {{
            position: relative;
            width: 300px;
            border: 1px solid #ccc;
            border-radius: 6px;
            padding: 6px;
        }}
        
        .multi-select input {{
            border: none;
            outline: none;
            width: 100%;
            cursor: pointer;
        }}
        
        .chips {{
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-bottom: 4px;
        }}
        
        .chip {{
            background: #e0e0e0;
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 12px;
            display: flex;
            align-items: center;
        }}
        
        .chip span {{
            margin-left: 6px;
            cursor: pointer;
        }}
        
        .dropdown {{
            position: absolute;
            background: white;
            border: 1px solid #ccc;
            width: 100%;
            max-height: 150px;
            overflow-y: auto;
            display: none;
            z-index: 10;
        }}
        
        .dropdown div {{
            padding: 6px;
            cursor: pointer;
        }}
        
        .dropdown div:hover {{
            background: #f0f0f0;
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

        .details-table {{
            width: max-content;       
            min-width: 100%;
            border-collapse: collapse;
            font-size: 0.95rem;
            table-layout: auto;       
        }}

        .details-table th {{
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

        .details-table td {{
            padding: 12px;
            border-bottom: 1px solid {theme['border_color']};
            vertical-align: top;
        }}
        
        .details-table tr:hover {{
            background: rgba(46, 134, 171, 0.04);
        }}
        
        .details-table tr:nth-child(even) {{
            background: rgba(0,0,0,0.02);
        }}
        
        .details-table tr:nth-child(even):hover {{
            background: rgba(46, 134, 171, 0.04);
        }}

        .details-table td:first-child,
        .details-table td:nth-child(2) {{
            white-space: normal;
            max-width: 600px;
        }}

        .details-table th {{
            position: sticky;
            top: 0;
            z-index: 10;
            resize: none;               
            overflow: hidden;
        }}

        .resizer {{
            position: absolute;
            right: 0;
            top: 0;
            width: 6px;
            height: 100%;
            cursor: col-resize;
            user-select: none;
        }}

        .details-table td {{
            white-space: normal;     
            word-break: break-word;
            max-width: 600px;
        }}

       .table-container {{
            overflow-x: auto;        
            overflow-y: visible;
            max-width: 100%;
        }}

        .metric-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }}
        
        .metric-table th,
        .metric-table td {{
            border: 1px solid #ddd;
            padding: 8px;
            vertical-align: top;
        }}
        
        .metric-table th {{
            background-color: #7393B3;
            font-weight: 600;
            text-transform: capitalize;
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
            transform: rotate(180deg);
        }}
        
        .toggle-icon.expanded {{
            transform: rotate(0deg);
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

        /* Metric sheet fields container tweaks */
        #metricSheetFields {{
            padding: 0;
            margin: 0;
        }}
        
        .modal-section h4 {{
            margin-bottom: 8px;
        }}

         .tab-content {{
             display: none;
             width: 100%;
         }}

        .tab-content {{
            display: none;
            width: 100%;
        }}
 
        .tab-content.active {{
            display: block;
            height: auto;
            overflow: visible;
        }}

        .charts-grid {{
            display: block;          
            width: 100%;
        }}
 
        .chart-card {{
            overflow: visible;
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
                            value = f'{value:.2f}'
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
            html.append('<table class="details-table">')
            html.append('<thead><tr>')
            html.append('<th>Question</th>')
            html.append('<th>Response</th>')
            
            # Add metric headers
            for metric in metrics:
                display_name = metric.replace('_', ' ').title()
                html.append(f'<th class="text-center">{display_name}</th>')
            
            html.append('<th>RCA</th>')
            
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

    def _generate_secondary_llm_table(self, df: pd.DataFrame, metrics: List[str]) -> str:
        try:
            if df.empty:
                return "<div class='text-center p-3'>No details data available</div>"
            html = []
            html.append('<div class="table-container">')
            html.append('<table class="details-table">')        
            html.append('<thead><tr>')
            html.append('<th>Question</th>')
            html.append('<th>Response</th>')
        
            for metric in metrics:
                html.append(f'<th>Primary_{metric}</th>')
                html.append(f'<th>Secondary_{metric}</th>')
        
            html.append('</tr></thead>')
            html.append('<tbody id="secondaryTableBody"></tbody>')
            html.append('</table>')
            html.append('</div>')

            html.append(self._generate_secondary_pagination_controls())

            html.append(self._generate_secondary_llm_javascript(df, metrics))
        
            return "\n".join(html)

        except Exception as e:
            logger.error(f"Error generating secondary llm table: {e}")
            return f"<div class='alert alert-error'>Error generating secondary llm table: {e}</div>"
    
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

    def _generate_secondary_pagination_controls(self) -> str:
        return """
        <div class="pagination-container">
            <div class="pagination-controls">
                <select id="secondaryRowsPerPage" class="rows-selector" onchange="secondaryChangeRowsPerPage()">
                    <option value="10">10 rows/page</option>
                    <option value="25">25 rows/page</option>
                    <option value="50">50 rows/page</option>
                    <option value="100">100 rows/page</option>
                </select>
            </div>
    
            <div class="pagination-controls" id="secondaryPaginationButtons"></div>
    
            <div class="page-info">
                <span id="secondaryPageInfo">Page 1 of 1</span>
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

            rca_df = self._load_rca_data()
            from collections import defaultdict
            rca_map = defaultdict(list)
            for _, row in rca_df.iterrows():
                key = self._normalize_text(row["Query"])
                rca_map[key].append(row.to_dict())
            
            for idx, row in df.iterrows():
                # Prepare query and response
                question_short = str(row.get('Query', 'N/A'))
                response_short = str(row.get('Response', 'N/A'))

                question_short = question_short.replace('\\n', '<br>').replace('\n', '<br>')
                response_short = response_short.replace('\\n', '<br>').replace('\n', '<br>')
                
                # Prepare metric data
                metric_cells = {}
                for metric in metrics:
                    status_col = f"{metric}_status"
                    status = row.get(status_col, 'Unknown')
                    score = row.get(metric, 'N/A')
                    
                    # Format score
                    if pd.notna(score) and isinstance(score, (int, float)):
                        formatted_score = f'{score:.2f}'
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
                
                lookup_key = self._normalize_text(question_short)
                rca_rows = rca_map.get(lookup_key, [])
                has_rca_match = len(rca_rows) > 0

                failure_category = ""
                
                if has_rca_match:
                    failure_category =  str(rca_rows[0].get("Failure Category", "")).strip().lower()
                
                table_data.append({
                    'index': int(idx),
                    'query': question_short,
                    'response': response_short,
                    'metrics': metric_cells,
                    'rca': {
                        "has_match": has_rca_match,
                        "failure_category": failure_category,
                        "details": [
                            {k: ("N/A" if pd.isna(v) else v) for k, v in r.items()}
                            for r in rca_rows
                        ] if rca_rows else {}
                    }
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

            document.addEventListener("DOMContentLoaded", function() {{
                const content = document.getElementById("responseContent");
                const icon = document.getElementById("responseIcon");
            
                if (content && icon && content.classList.contains("collapsed")) {{
                    icon.classList.remove("expanded");  // ▲ when closed
                }}
            }});
            
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
                    html += `<td>${{rowData.query}}</td>`;
                    html += `<td>${{rowData.response}}</td>`;
                    
                    // Metric columns
                    allMetrics.forEach(metric => {{
                        const metricData = rowData.metrics[metric]  || {{
                                value: "N/A",
                                status: "Skipped",
                                class: "status-skipped",
                                clickable: false
                        }};
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

                    const rca = rowData.rca;
                    if (rca && rca.has_match) {{
                        const fc = (rca.failure_category || "").toLowerCase();
                        const isNone = !fc || fc === "none";

                        const colorClass = isNone ? "status-passed" : "status-failed";
                        const label = isNone ? "No Violation" : "Violation";
                    
                        html += `
                    <td class="text-center">
                    <span class="status-cell ${{colorClass}}"
                                onclick="openRcaModal(${{i}})"
                                title="Click for RCA">
                                ${{label}}
                    </span>
                    </td>`;
                    }} else {{
                        html += `<td class="text-center">N/A</td>`;
                    }}   

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

            document.addEventListener("DOMContentLoaded", () => {{
                const table = document.querySelector(".details-table");
                if (!table) return;
            
                const ths = table.querySelectorAll("th");
            
                ths.forEach((th, index) => {{
                    const resizer = document.createElement("div");
                    resizer.className = "resizer";
                    th.appendChild(resizer);
            
                    let startX, startWidth;
            
                    resizer.addEventListener("mousedown", (e) => {{
                        startX = e.pageX;
                        startWidth = th.offsetWidth;
            
                        document.addEventListener("mousemove", onMouseMove);
                        document.addEventListener("mouseup", onMouseUp);
                    }});
            
                    function onMouseMove(e) {{
                        const newWidth = startWidth + (e.pageX - startX);
                        if (newWidth > 50) {{
                            th.style.width = newWidth + "px";
                            syncColumnWidth(index, newWidth);
                        }}
                    }}
            
                    function onMouseUp() {{
                        document.removeEventListener("mousemove", onMouseMove);
                        document.removeEventListener("mouseup", onMouseUp);
                    }}
                }});
            
                function syncColumnWidth(colIndex, width) {{
                    const rows = table.querySelectorAll("tr");
                    rows.forEach(row => {{
                        const cell = row.children[colIndex];
                        if (cell) {{
                            cell.style.width = width + "px";
                        }}
                    }});
                }}
            }});
            </script>
            """
            
        except Exception as e:
            logger.error(f"Error generating table JavaScript: {e}")
            return f"<script>console.error('Error generating table JavaScript: {e}');</script>"

    def _generate_secondary_llm_javascript(self, df: pd.DataFrame, metrics: List[str]) -> str:
        try:
            table_data = []

            for idx, row in df.iterrows():
                # Prepare query and response
                question_short = str(row.get('Query', 'N/A'))
                response_short = str(row.get('Response', 'N/A'))

                question_short = question_short.replace('\\n', '<br>').replace('\n', '<br>')
                response_short = response_short.replace('\\n', '<br>').replace('\n', '<br>')

                query_key = self._normalize_query_match(question_short)
                
                # Prepare metric data
                metric_cells = {}
                for metric in metrics:
                    status_col = f"{metric}_status"
                    status = row.get(status_col, 'Unknown')
                    score = row.get(metric, 'N/A')
                    
                    # Format score
                    if pd.notna(score) and isinstance(score, (int, float)):
                        formatted_score = f'{score:.2f}'
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

                table_data.append({'index': int(idx),
                    'query': question_short,
                    'query_key': query_key,
                    'response': response_short,
                    'metrics': metric_cells
                })

            secondary_meta_map = {}  # normalized eval_name -> list of row dicts (excluding eval_name & trace_id)
            try:
                # Prefer the configured metric_details_excel_path, else fallback to Metrics_template.xlsx near the script
                excel_candidates = []
                if self.metric_details_excel_path and self.metric_details_excel_path.exists():
                    excel_candidates.append(self.metric_details_excel_path)
                # fallback candidate
                base_dir = Path(__file__).resolve().parent
                fallback_path = base_dir / "Metrics_template.xlsx"
                if fallback_path.exists():
                    excel_candidates.append(fallback_path)
    
                loaded = False
                sec_df = None
                for excel_file in excel_candidates:
                    try:
                        xls = pd.ExcelFile(excel_file)
                        if "Secondary LLM" in xls.sheet_names:
                            sec_df = pd.read_excel(xls, sheet_name="Secondary LLM")
                            loaded = True
                            break
                    except Exception:
                        continue
    
                if loaded and sec_df is not None:
                    # Normalize column names to strings and strip
                    sec_df = sec_df.rename(columns=lambda c: str(c).strip())
                    # Build mapping grouped by eval_name (case-insensitive)
                    for _, srow in sec_df.iterrows():
                        eval_name = str(srow.get("Eval_Name", "")).strip()
                        query_val = str(srow.get("Query", "")).strip()

                        if not eval_name:
                            continue

                        metric_key = eval_name.strip().lower()
                        query_key = self._normalize_query_match(query_val)

                        # Build a dict of remaining fields excluding eval_name and trace_id
                        meta = {}
                        for col in sec_df.columns:
                            col_clean = str(col).strip().lower()
                            if col_clean in ("Eval_Name", "trace_id"):
                                continue
                            # Convert NaN to None for JSON friendliness
                            val = srow.get(col)
                            if pd.isna(val):
                                val = None
                            meta[col] = val

                        secondary_meta_map.setdefault(metric_key, {}).setdefault(query_key, []).append(meta)
            except Exception as e:
                # If anything fails, keep secondary_meta_map empty (graceful fallback)
                logger.warning(f"Unable to read Secondary LLM sheet: {e}")
                secondary_meta_map = {}
        
            # Convert Python structures to JSON for JS usage
            table_data_json = json.dumps(table_data)
            metrics_json = json.dumps(metrics)
            secondary_meta_json = json.dumps(secondary_meta_map)
                
            return f"""
                <script>
                let secondaryCurrentPage = 1;
                let secondaryRowsPerPage = 10;
                const secondaryTableData = {json.dumps(table_data)};
                const secondaryMetaMap = {secondary_meta_json};
                let allSecondaryMetrics = {metrics_json};
                
                function renderSecondaryTable() {{
                    const tbody = document.getElementById("secondaryTableBody");
                    if (!tbody) return;
                
                    const start = (secondaryCurrentPage - 1) * secondaryRowsPerPage;
                    const end = Math.min(start + secondaryRowsPerPage, secondaryTableData.length);
                
                    let html = "";
                
                    for (let i = start; i < end; i++) {{
                        const row = secondaryTableData[i];
                        html += "<tr>";
                        html += `<td>${{row.query}}</td>`;
                        html += `<td>${{row.response}}</td>`;

                        allSecondaryMetrics.forEach(metric => {{
                            const metricSecondaryData = row.metrics[metric] || {{
                                value: "N/A",
                                class: "status-skipped",
                                clickable: false
                            }};
                            if (metricSecondaryData.clickable) {{
                                html += `<td class="text-center">
                                    <span class="status-cell ${{metricSecondaryData.class}}" 
                                        onclick="openModal(${{row.index}}, '${{metric}}')"
                                        title="Click for details">
                                        ${{metricSecondaryData.value}}
                                    </span>
                                </td>`;
                            }} else {{
                                html += `<td class="text-center">
                                    <span class="status-cell status-skipped">N/A</span>
                                </td>`;
                            }}

                            // Secondary column: render label (error_type) + colored button
                            const metricMap = secondaryMetaMap[metric.toLowerCase()] || {{}};
                            const metaList = metricMap[row.query_key] || [];
                            const meta = metaList.length > 0 ? metaList[0] : null;
                            const errorType = (meta && meta.error_type != null && meta.error_type !== "") ? String(meta.error_type) : "none";
                            let btnClass = "status-passed";
                            let btnLabel = "No Violation";
                            if (errorType.toLowerCase() !== "none") {{
                                btnClass = "status-failed";
                                btnLabel = errorType;
                            }} else {{
                                btnClass = "status-passed";
                            }}
                            html += `
                                <td class="text-center">
                                    <button class="status-cell ${{btnClass}}" onclick="openSecondaryModal(${{i}}, '${{escapeHtml(metric)}}')" style="border:none; padding:8px 10px; border-radius:8px;">
                                        ${{btnLabel}}
                                    </button>
                                </td>`;
                        }});
                
                        html += "</tr>";
                    }}
                
                    tbody.innerHTML = html;
                    updateSecondaryPaginationInfo();
                }}
                
                function updateSecondaryPaginationInfo() {{
                    const totalPages = Math.ceil(
                        secondaryTableData.length / secondaryRowsPerPage
                    );
                
                    document.getElementById("secondaryPageInfo").innerText =
                        `Page ${{secondaryCurrentPage}} of ${{totalPages}}`;
                
                    renderSecondaryPaginationButtons();
                }}

                function renderSecondaryPaginationButtons() {{
                    const container = document.getElementById("secondaryPaginationButtons");
                    if (!container) return;
                
                    const totalPages = Math.ceil(
                        secondaryTableData.length / secondaryRowsPerPage
                    );
                
                    container.innerHTML = `
                <button class="page-btn"
                            onclick="secondaryPreviousPage()"
                            ${{secondaryCurrentPage === 1 ? "disabled" : ""}}>
                            Prev
                </button>
                
                        <span class="page-btn disabled">
                            ${{secondaryCurrentPage}} / ${{totalPages}}
                </span>
                
                        <button class="page-btn"
                            onclick="secondaryNextPage()"
                            ${{secondaryCurrentPage === totalPages ? "disabled" : ""}}>
                            Next
                </button>
                    `;
                }}
                
                function goToPage(page) {{
                    const totalPages = Math.ceil(secondaryTableData.length / secondaryRowsPerPage);
                    if (page >= 1 && page <= totalPages) {{
                        secondaryCurrentPage = page;
                        renderSecondaryTable();
                    }}
                }}

                function secondaryNextPage() {{
                    const totalPages = Math.ceil(
                        secondaryTableData.length / secondaryRowsPerPage
                    );
                    if (secondaryCurrentPage < totalPages) {{
                        secondaryCurrentPage++;
                        renderSecondaryTable();
                    }}
                }}
                
                function secondaryPreviousPage() {{
                    if (secondaryCurrentPage > 1) {{
                        secondaryCurrentPage--;
                        renderSecondaryTable();
                    }}
                }}

                function secondaryChangeRowsPerPage() {{
                    const select = document.getElementById("secondaryRowsPerPage");
                    secondaryRowsPerPage = parseInt(select.value);
                    secondaryCurrentPage = 1;
                    renderSecondaryTable();
                }}

                function openSecondaryModal(rowIndex, metricName) {{
                    const tb = document.getElementById('tracebackFields');
                    if (tb) tb.innerHTML = ''
                    const modal = document.getElementById('detailModal');
                    if (!modal) return;
                    // Hide left sections to reuse modal for meta display cleanly
                    const leftSections = modal.querySelectorAll('.modal-left .modal-section');
                    leftSections.forEach(s => s.style.display = 'none');
                    const collapsible = modal.querySelector('.collapsible-section');
                    if (collapsible) collapsible.style.display = 'none';
                    const modalRight = modal.querySelector('.modal-right');
                    if (modalRight) modalRight.style.display = 'none';
    
                    document.getElementById('modalTitle').textContent = `${{metricName}} - Secondary LLM Details`;
                    document.getElementById('modalSubtitle').textContent = '';
    
                    const container = document.getElementById('metricSheetFields');
                    container.innerHTML = '';

                    const row = secondaryTableData[rowIndex];
                    const qKey = row.query_key;

                    const metricMap = secondaryMetaMap[metricName.toLowerCase()] || {{}}; 
                    const metaList = metricMap[qKey] || [];
                    if (metaList.length === 0) {{
                        const section = document.createElement('div');
                        section.className = 'modal-section';
                        section.innerHTML = '<h4>No metadata</h4><p>N/A</p>';
                        container.appendChild(section);
                    }} else {{
                        metaList.forEach((meta, idx) => {{
                            const keys = Object.keys(meta || {{}}).filter(k => k && k.toLowerCase() !== 'Eval_Name' && k.toLowerCase() !== 'trace_id');
                            if (keys.length === 0) {{
                                const section = document.createElement('div');
                                section.className = 'modal-section';
                                section.innerHTML = `<h4>Row ${{idx+1}}</h4><p>N/A</p>`;
                                container.appendChild(section);
                            }} else {{
                                keys.forEach(k => {{
                                    let v = meta[k];
                                    const section = document.createElement('div');
                                    section.className = 'modal-section';
                                    const heading = document.createElement('h4');
                                    heading.textContent = String(k).replace(/_/g, ' ');
                                    section.appendChild(heading);
                                    const content = document.createElement('div');
                                    if (v === null || v === undefined) {{
                                        content.innerHTML = '<p>N/A</p>';
                                    }} else if (typeof v === 'object') {{
                                        const formatted = escapeHtml(JSON.stringify(v, null, 2)).replace(/\\n/g, "<br>");
                                        content.innerHTML = `<pre>${{formatted}}</pre>`;
                                    }} else {{
                                        const formatted = escapeHtml(String(v)).replace(/\\n/g, "<br>");
                                        content.innerHTML = `<p>${{formatted}}</p>`;
                                    }}
                                    section.appendChild(content);
                                    container.appendChild(section);
                                }});
                            }}
                        }});
                    }}
    
                    modal.style.display = 'block';
                }}
    
                // helper escape (duplicate from main script to keep safe)
                function escapeHtml(str) {{
                    if (str === null || str === undefined) return '';
                    return String(str)
                        .replace(/&/g, '&amp;')
                        .replace(/</g, '&lt;')
                        .replace(/>/g, '&gt;')
                        .replace(/"/g, '&quot;')
                        .replace(/'/g, '&#39;');
                }}
                
                document.addEventListener("DOMContentLoaded", renderSecondaryTable);
                </script>
                """
        except Exception as e:
            logger.error(f"Error generating secondary llm javascript: {e}")
            return f"<script>console.error('Error generating secondary llm javascript: {e}');</script>"
 
    
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
            metrics_count = metrics_df['Metrics'].notna().sum()
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
                📊 Metrics Summary ({metrics_count})
            </button>
            <button class="tab-button" onclick="showTab('analytics', event)">
                📈 Analytics Dashboard
            </button>
            <button class="tab-button" onclick="showTab('details', event)">
                🔍 Detailed Results
            </button>
            <button class="tab-button" onclick="showTab('secondary_llm', event)">
                🤖 Secondary LLM
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
                            <div style="overflow-x:auto; width:100%;">
                                {charts.get('comparison', '<div>No comparison chart data available</div>')}
                        </div>
                        </div>
                    </div>
                    
                    <div class="chart-card full-width">
                        <div class="card-header">
                            <h3>📋 Metrics Overview by Status</h3>
                        </div>
                        <div class="card-content">
                            <div style="overflow-x:auto; width:100%;">
                                {charts.get('metrics', '<div>No metrics chart data available</div>')}
                            </div>
                        </div>
                    </div>

                    <div class="chart-card full-width">
                        <div class="card-header">
                            <h3>📦 Data Coverage</h3>
                        </div>
                        <div class="card-content">
                                {charts.get('coverage', '<div>No coverage data available</div>')}
                        </div>
                    </div>
                            
                    <div class="chart-card full-width">
                        <div class="card-header">
                            <h3>🔁 Run Comparison</h3>
                        </div>
                        <div class="card-content">
                            <input type="file" id="prevRun">
                            <input type="file" id="currRun">
                            <br><br>
                            <button onclick="uploadRuns()">Compare Runs</button>
                            
                            <div id="runComparisonResult" style="margin-top:20px;">
                                <i>Upload files to compare runs</i>
                            </div>
                        </div>
                    </div>
                            
                    <div class="chart-card full-width">
                        <div class="card-header">
                            <h3>📊 Aggregated Metrics Score</h3>
                        </div>
                        <div class="card-content">
                            {charts.get('aggregated', '<div>No aggregated data available</div>')}
                        </div>
                    </div>
                            
                    <div class="chart-card full-width">
                        <div class="card-content">
                                {charts.get('disaggregated', '<div>No disaggregated data available</div>')}
                        </div>
                    </div>
                </div>
            </div>
            
            <div id="details" class="tab-content">
                <div class="card-content p-0">
                    {self._generate_interactive_details_table(details_df, all_metrics)}
                </div>
            </div>
            
            <div id="secondary_llm" class="tab-content">
                <div class="card-content">
                    {self._generate_secondary_llm_table(details_df, all_metrics)}
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
        
        function toggleCollapsible(section) {{
            const content = document.getElementById(section + "Content");
            const icon = document.getElementById(section + "Icon");
            if (!content || !icon) return;
            const isCollapsed = content.classList.contains("collapsed");
            if (isCollapsed) {{
                content.classList.remove("collapsed");
                icon.classList.add("expanded");   // ▼
            }} else {{
                content.classList.add("collapsed");
                icon.classList.remove("expanded"); // ▲
            }}
        }}
        
        // Updated openModal + helpers: renders column headings once and shows values under each heading.
        // Replace your existing openModal with this function.
        
        // Add these helpers and the updated openModal in the JS file where openModal is defined
 
        function escapeHtml(str) {{
            if (str === null || str === undefined) return '';
            return String(str)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }}
        
        function renderArrayOfObjectsAsColumns(arr) {{
        if (!Array.isArray(arr) || arr.length === 0) return '<div class="modal-section"><p>N/A</p></div>';
        
        const keySet = new Set();
        arr.forEach(row => {{
            if (row && typeof row === 'object' && !Array.isArray(row)) {{
            Object.keys(row).forEach(k => keySet.add(k));
            }}
        }});
        const keys = Array.from(keySet);
        if (keys.length === 0) {{
            const vals = arr.filter(v => v !== null && v !== undefined && v !== '').map(v => escapeHtml(String(v)));
            return `<div class="modal-section"><p>${{vals.join('<br/>') || 'N/A'}}</p></div>`;
        }}
        
        let html = `<div class="modal-grid">`;
        keys.forEach(key => {{
            const prettyKey = key.replace(/_/g, ' ');
            const values = arr.map(row => {{
            if (!row || !(key in row)) return null;
            const v = row[key];
            if (v === null || v === undefined || v === '' || String(v).toLowerCase() === 'nan' || String(v) === 'N/A') return null;
            if (typeof v === 'object') return `<pre>${{escapeHtml(JSON.stringify(v, null, 2))}}</pre>`;
            return escapeHtml(String(v));
            }}).filter(Boolean);
        
            html += `<div class="modal-section"><h4>${{escapeHtml(prettyKey)}}</h4>`;
            html += (values.length === 0) ? `<p>N/A</p>` : `<p>${{values.join('<br/>')}}</p>`;
            html += `</div>`;
        }});
        html += `</div>`;
        return html;
        }}
        
        function renderObjectAsColumns(obj) {{
        if (!obj || typeof obj !== 'object') return `<div class="modal-section"><p>N/A</p></div>`;
        const entries = Object.entries(obj);
        if (entries.length === 0) return `<div class="modal-section"><p>N/A</p></div>`;
        
        let html = `<div class="modal-grid">`;
        entries.forEach(([k, v]) => {{
            const prettyKey = k.replace(/_/g, ' ');
            html += `<div class="modal-section"><h4>${{escapeHtml(prettyKey)}}</h4>`;
            if (v === null || v === undefined || v === '' || String(v).toLowerCase() === 'nan' || String(v) === 'N/A') {{
            html += `<p>N/A</p>`;
            }} else if (typeof v === 'object') {{
            if (Array.isArray(v)) {{
                const vals = v.map(x => (x === null || x === undefined) ? null : (typeof x === 'object' ? `<pre>${{escapeHtml(JSON.stringify(x, null, 2))}}</pre>` : escapeHtml(String(x)))).filter(Boolean);
                html += `<p>${{vals.join('<br/>') || 'N/A'}}</p>`;
            }} else {{
                html += `<pre>${{escapeHtml(JSON.stringify(v, null, 2))}}</pre>`;
            }}
            }} else {{
            html += `<p>${{escapeHtml(String(v))}}</p>`;
            }}
            html += `</div>`;
        }});
        html += `</div>`;
        return html;
        }}
        
        function renderMetricFieldsAsHeadings(objOrArray) {{
            if (objOrArray === null || objOrArray === undefined) return `<div class="modal-section"><p>N/A</p></div>`;
            if (Array.isArray(objOrArray)) {{
                if (objOrArray.length > 0 && objOrArray.every(item => typeof item === 'object' && !Array.isArray(item))) {{
                return renderArrayOfObjectsAsColumns(objOrArray);
                }}
                const vals = objOrArray.map(v => (v === null || v === undefined) ? null : (typeof v === 'object' ? `<pre>${{escapeHtml(JSON.stringify(v, null, 2))}}</pre>` : escapeHtml(String(v)))).filter(Boolean);
                return `<div class="modal-section"><p>${{vals.join('<br/>') || 'N/A'}}</p></div>`;
            }}
            if (typeof objOrArray === 'object') {{
                return renderObjectAsColumns(objOrArray);
            }}
            return `<div class="modal-section"><p>${{escapeHtml(String(objOrArray))}}</p></div>`;
        }}
        
        function openModal(rowIndex, metricName) {{
            document.querySelector(".modal-left .modal-section").style.display = "block";
            document.querySelector(".collapsible-section").style.display = "block";
            document.querySelector(".modal-right").style.display = "block";
            const modal = document.getElementById('detailModal');
            if (!modal || !modalData[rowIndex]) {{
                console.error('Modal or data not found');
                return;
            }}
        
            const data = modalData[rowIndex];
            const metricData = data.metrics[metricName] || {{}};
            const metricSheetData = data.metric_fields?.[metricName] || {{}}; // object or array
        
            // Reset modal scroll positions
            const modalLeft = modal.querySelector('.modal-left');
            const modalRight = modal.querySelector('.modal-right');
            if (modalLeft) modalLeft.scrollTop = 0;
            if (modalRight) modalRight.scrollTop = 0;
        
            // Reset response collapsible to collapsed state for a clean start
            const responseContent = document.getElementById('responseContent');
            const responseIcon = document.getElementById('responseIcon');
            if (responseContent && responseIcon) {{
                responseContent.classList.add('collapsed');
                responseIcon.classList.remove('expanded');
                responseIcon.textContent = '▼';
            }}
        
            // Helper to set text
            const updateElementText = (id, content) => {{
                const el = document.getElementById(id);
                if (!el) return;
                if (content === null || content === undefined || content === '') {{
                    el.innerHTML = 'N/A';
                    return;
                }}
            
                el.innerHTML = content;
            }};
        
            updateElementText('modalTitle', `${{metricName.replace(/_/g, ' ').toUpperCase()}}`);
            updateElementText('modalSubtitle', `Threshold: ${{metricData.threshold || 'N/A'}}`);
            updateElementText('modalQuestion', data.query);
            updateElementText('modalResponse', data.response);
 
            /* ============================
            TRACEBACK TABLE (PRIMARY ONLY)
            ============================ */
            
            let uniqueTracebacks = [];
            const tracebackContainer = document.getElementById('tracebackFields');
            if (tracebackContainer) tracebackContainer.innerHTML = '';
            
            // detect modal type from title
            const modalTitleText = document.getElementById('modalTitle')?.textContent || '';
            const isSecondaryModal = modalTitleText.toLowerCase().includes('secondary');
            const isRcaModal = modalTitleText.toLowerCase().includes('rca');
            
            // show traceback ONLY for primary metric modal
            if (!isSecondaryModal && !isRcaModal && tracebackContainer) {{
            
                let tbRows = [];
                if (Array.isArray(metricSheetData)) tbRows = metricSheetData;
                else if (metricSheetData && typeof metricSheetData === 'object') tbRows = [metricSheetData];
            
                if (tbRows.length > 0) {{
            
                    const TRACE_KEYS = Object.keys(tbRows[0]).filter(
                        k => ['traceback','tracebacks'].includes(k.toLowerCase())
                    );
            
                    if (TRACE_KEYS.length > 0) {{
            
                        // deduplicate
                        tbRows.forEach(row => {{
                            const obj = {{}};
                            TRACE_KEYS.forEach(k => obj[k] = row[k]);
                            const s = JSON.stringify(obj);
                            if (!uniqueTracebacks.some(u => JSON.stringify(u) === s)) {{
                                uniqueTracebacks.push(obj);
                            }}
                        }});
            
                        if (uniqueTracebacks.length > 0) {{
            
                            function parseVal(v){{
                                if (typeof v === 'string') {{
                                    try {{ return JSON.parse(v); }} catch(e){{}}
                                }}
                                return v;
                            }}
            
                            function primitiveTD(v){{
                                const td = document.createElement('td');
                                td.innerHTML =
                                    v === null || v === undefined || String(v).toLowerCase()==='nan'
                                        ? 'N/A'
                                        : String(v).replace(/\\n/g, "<br>");
                                return td;
                            }}

                            function stripHtml(value){{
                                if (typeof value !== 'string') return value;
                            
                                const div = document.createElement('div');
                                div.innerHTML = value;
                                return div.textContent || div.innerText || '';
                            }}
            
                            function renderCell(val){{
                                // parse JSON string if needed
                                if (typeof val === 'string'){{
                                    try {{ val = JSON.parse(val); }} catch(e){{}}
                                }}
                            
                                // ---------- ARRAY ----------
                                if (Array.isArray(val)){{
                            
                                    if (!val.length){{
                                        const td=document.createElement('td');
                                        td.textContent='N/A';
                                        return td;
                                    }}
                            
                                    // array of objects → table
                                    if (typeof val[0]==='object'){{
                            
                                        const table=document.createElement('table');
                                        table.className='metric-table';
                            
                                        const thead=document.createElement('thead');
                                        const trh=document.createElement('tr');
                            
                                        Object.keys(val[0]).forEach(k=>{{
                                            const th=document.createElement('th');
                                            th.textContent=k.replace(/_/g,' ');
                                            trh.appendChild(th);
                                        }});
                            
                                        thead.appendChild(trh);
                                        table.appendChild(thead);
                            
                                        const tbody=document.createElement('tbody');
                            
                                        val.forEach(obj=>{{
                                            const tr=document.createElement('tr');
                                            Object.keys(val[0]).forEach(k=>{{
                                                const td=renderCell(obj[k]);   // recursion
                                                tr.appendChild(td);
                                            }});
                                            tbody.appendChild(tr);
                                        }});
                            
                                        table.appendChild(tbody);
                            
                                        const td=document.createElement('td');
                                        td.appendChild(table);
                                        return td;
                                    }}
                            
                                    // primitive array
                                    const td=document.createElement('td');
                                    td.textContent=val.map(v => stripHtml(v)).join(', ');
                                    return td;
                                }}
                            
                                // ---------- OBJECT ----------
                                if (val && typeof val==='object'){{
                            
                                    const table=document.createElement('table');
                                    table.className='metric-table';
                            
                                    const thead=document.createElement('thead');
                                    const trh=document.createElement('tr');
                            
                                    Object.keys(val).forEach(k=>{{
                                        const th=document.createElement('th');
                                        th.textContent=k.replace(/_/g,' ');
                                        trh.appendChild(th);
                                    }});
                            
                                    thead.appendChild(trh);
                                    table.appendChild(thead);
                            
                                    const tbody=document.createElement('tbody');
                                    const tr=document.createElement('tr');
                            
                                    Object.keys(val).forEach(k=>{{
                                        const td=renderCell(val[k]);   // recursion
                                        tr.appendChild(td);
                                    }});
                            
                                    tbody.appendChild(tr);
                                    table.appendChild(tbody);
                            
                                    const td=document.createElement('td');
                                    td.appendChild(table);
                                    return td;
                                }}
                            
                                // ---------- PRIMITIVE ----------
                                const td=document.createElement('td');
                                let cleanVal = stripHtml(val);
                                td.textContent =
                                    cleanVal===null || cleanVal===undefined || String(cleanVal).toLowerCase()==='nan'
                                        ? 'N/A'
                                        : cleanVal;
                                return td;
                            }}
            
                            // build table
                            const heading = document.createElement('div');
                            heading.textContent = "Traceback";
                            heading.style.fontSize = "18px";
                            heading.style.fontWeight = "700";
                            heading.style.margin = "10px 0 6px 0";
                            heading.style.color = "#2E86AB";
                            tracebackContainer.appendChild(heading);

                            const table=document.createElement('table');
                            table.className='metric-table';
            
                            const thead=document.createElement('thead');
                            const trHead=document.createElement('tr');
            
                            if (TRACE_KEYS.length===1){{
                                let sample=parseVal(uniqueTracebacks[0][TRACE_KEYS[0]]);
                                if (sample && typeof sample==='object' && !Array.isArray(sample)){{
                                    Object.keys(sample).forEach(k=>{{
                                        const th=document.createElement('th');
                                        th.textContent=k.replace(/_/g,' ');
                                        trHead.appendChild(th);
                                    }});
                                }}else{{
                                    const th=document.createElement('th');
                                    th.textContent=TRACE_KEYS[0];
                                    trHead.appendChild(th);
                                }}
                            }}else{{
                                TRACE_KEYS.forEach(h=>{{
                                    const th=document.createElement('th');
                                    th.textContent=h.replace(/_/g,' ');
                                    trHead.appendChild(th);
                                }});
                            }}
            
                            thead.appendChild(trHead);
                            table.appendChild(thead);
            
                            const tbody=document.createElement('tbody');
            
                            uniqueTracebacks.forEach(row=>{{
                                const tr=document.createElement('tr');
            
                                if (TRACE_KEYS.length===1){{
                                    let val=parseVal(row[TRACE_KEYS[0]]);
                                    if (val && typeof val==='object' && !Array.isArray(val)){{
                                        Object.values(val).forEach(v=>{{
                                            tr.appendChild(renderCell(v));
                                        }});
                                    }}else{{
                                        tr.appendChild(renderCell(val));
                                    }}
                                }}else{{
                                    TRACE_KEYS.forEach(h=>{{
                                        tr.appendChild(renderCell(row[h]));
                                    }});
                                }}
            
                                tbody.appendChild(tr);
                            }});
            
                            table.appendChild(tbody);
                            tracebackContainer.appendChild(table);
                        }}
                    }}
                }}
            }}

            const metricFieldsContainer = document.getElementById('metricSheetFields');
            if (metricFieldsContainer) {{
                metricFieldsContainer.innerHTML = '';

                // ===== Metric Fields heading =====
                const mfHeading = document.createElement('div');
                mfHeading.textContent = "Metric Fields";
                mfHeading.style.fontSize = "18px";
                mfHeading.style.fontWeight = "700";
                mfHeading.style.margin = "14px 0 6px 0";
                mfHeading.style.color = "#2E86AB";
                metricFieldsContainer.appendChild(mfHeading);

                requestAnimationFrame(() => {{
                    try {{
                        const tbContainer = document.getElementById('tracebackFields');
                        const mfContainer = document.getElementById('metricSheetFields');
                        if (!tbContainer || !mfContainer) return;
                
                        const getHeaders = (container) => {{
                            const table = container.querySelector('table.metric-table');
                            if (!table) return "";
                
                            const ths = table.querySelectorAll('th');
                            return Array.from(ths)
                                .map(th => th.innerText.trim().toLowerCase())
                                .join("|");
                        }};
                
                        const tbCols = getHeaders(tbContainer);
                        const mfCols = getHeaders(mfContainer);
                                
                        if (tbCols && mfCols && tbCols === mfCols) {{
                            mfContainer.innerHTML = "";   // hide Metric Fields
                        }}
                
                    }} catch(e) {{
                        console.error("Column compare error:", e);
                    }}
                }});

                // Normalize rows
                let rows = [];
                if (Array.isArray(metricSheetData)) {{
                    rows = metricSheetData;
                }} else if (metricSheetData && typeof metricSheetData === 'object') {{
                    rows = [metricSheetData];
                }}
            
                if (rows.length === 0) {{
                    metricFieldsContainer.innerHTML = '<p>N/A</p>';
                    return; 
                }}

                function normalizeVal(v) {{
                    if (v === null || v === undefined) return '';
                    if (typeof v === 'string') {{
                        return v
                            .replace(/<[^>]*>/g,'')   // strip HTML
                            .replace(/\\s+/g,' ')     // normalize spaces
                            .trim()
                            .toLowerCase();
                    }}
                    return JSON.stringify(v);
                }}
            
                /* ======================================================
                CASE 1: MULTIPLE RECORDS → TABLE
                ====================================================== */
                if (rows.length > 1) {{
                    const excludeKeys = new Set([
                        'query','response','score','overall reason','overall_reason',
                        'overall score','overall_score','eval_name','timestamp','traceback','tracebacks'
                    ]);
                
                    // all candidate columns
                    const allHeaders = Object.keys(rows[0]).filter(
                        k => !excludeKeys.has(k.toLowerCase())
                    );
                
                    const constantCols = [];
                    const variableCols = [];
                
                    // detect constant vs variable
                    allHeaders.forEach(col => {{
                        const firstVal = normalizeVal(rows[0][col]);
                        const same = rows.every(r => normalizeVal(r[col]) === firstVal);
                        if (same) constantCols.push(col);
                        else variableCols.push(col);
                    }});
                
                    // ===== render constant columns outside =====
                    constantCols.forEach(col => {{
                        const section = document.createElement('div');
                        section.className = 'modal-section';
                
                        const heading = document.createElement('h4');
                        heading.textContent = col.replace(/_/g,' ');
                        section.appendChild(heading);
                
                        const content = document.createElement('div');
                        const v = rows[0][col];
                        content.innerHTML =
                            v === null || v === undefined || String(v).toLowerCase()==='nan'
                                ? 'N/A'
                                : String(v).replace(/\\n/g,"<br>");
                        section.appendChild(content);
                
                        metricFieldsContainer.appendChild(section);
                    }});
                
                    // ===== build table ONLY if variable columns exist =====
                    if (variableCols.length > 0) {{
                
                        const table = document.createElement('table');
                        table.className = 'metric-table';
                
                        // header
                        const thead = document.createElement('thead');
                        const trHead = document.createElement('tr');
                        variableCols.forEach(col => {{
                            const th = document.createElement('th');
                            th.textContent = col.replace(/_/g,' ');
                            trHead.appendChild(th);
                        }});
                        thead.appendChild(trHead);
                        table.appendChild(thead);
                
                        // body
                        const tbody = document.createElement('tbody');
                        rows.forEach(row => {{
                            const tr = document.createElement('tr');
                            variableCols.forEach(col => {{
                                const td = document.createElement('td');
                                const v = row[col];
                                td.innerHTML =
                                    v === null || v === undefined || String(v).toLowerCase()==='nan'
                                        ? 'N/A'
                                        : String(v).replace(/\\n/g,"<br>");
                                tr.appendChild(td);
                            }});
                            tbody.appendChild(tr);
                        }});
                
                        table.appendChild(tbody);
                        metricFieldsContainer.appendChild(table);
                    }}
                }}
            
                /* ======================================================
                CASE 2: SINGLE RECORD → PRESERVE OLD LAYOUT
                ====================================================== */
                else {{
                    const record = rows[0];
                    const excludeKeys = new Set([
                    'query', 'response', 'score', 'overall reason', 'overall_reason',
                    'overall score', 'overall_score', 'eval_name', 'timestamp', 'traceback', 'tracebacks'
                    ]);
            
                    Object.entries(record).forEach(([key, value]) => {{
                        if (excludeKeys.has(key.toLowerCase())) return;
                        if (
                            value === null ||
                            value === undefined ||
                            String(value).trim() === '' ||
                            String(value).toLowerCase() === 'nan'
                        ) return;
            
                        const section = document.createElement('div');
                        section.className = 'modal-section';
            
                        const heading = document.createElement('h4');
                        heading.textContent = key.replace(/_/g, ' ');
                        section.appendChild(heading);
            
                        const content = document.createElement('div');
                        content.innerHTML = String(value).replace(/\\n/g, "<br>");
                        section.appendChild(content);
            
                        metricFieldsContainer.appendChild(section);
                    }});
            
                    if (!metricFieldsContainer.hasChildNodes()) {{
                        metricFieldsContainer.innerHTML = '<p></p>';
                    }}
                }}
            }}

            // Update reason and additionalMetricFields
            updateElementText('modalReason', metricData.additional_fields?.reason || 'No reason provided');
        
            const additionalFieldsDiv = document.getElementById('additionalMetricFields');
            if (additionalFieldsDiv && metricData.additional_fields) {{
                additionalFieldsDiv.innerHTML = '';
                const processedFields = new Set(['reason', 'status']);
                Object.keys(metricData.additional_fields).forEach(fieldName => {{
                    if (!processedFields.has(fieldName)) {{
                        const fieldValue = metricData.additional_fields[fieldName];
                        if (fieldValue && String(fieldValue).toLowerCase() !== 'nan' && String(fieldValue) !== 'N/A') {{
                            const fieldDiv = document.createElement('div');
                            fieldDiv.className = 'modal-section';
                            const title = escapeHtml(fieldName.charAt(0).toUpperCase() + fieldName.slice(1).replace(/_/g, ' '));
                            if (typeof fieldValue === 'object') {{
                                fieldDiv.innerHTML = `<h4>${{title}}</h4><pre>${{escapeHtml(JSON.stringify(fieldValue, null, 2))}}</pre>`;
                            }} else {{
                                fieldDiv.innerHTML = `<h4>${{title}}</h4><p>${{escapeHtml(String(fieldValue))}}</p>`;
                            }}
                            additionalFieldsDiv.appendChild(fieldDiv);
                        }}
                    }}
                }});
            }}
        
            // Score visualization
            const scoreElement = document.getElementById('scorePieChart');
            if (scoreElement && metricData.score && metricData.threshold) {{
                createScorePieChart(
                    parseFloat(metricData.score),
                    parseFloat(metricData.threshold),
                    metricName
                );
            }}
        
            modal.style.display = 'block';
        }}

        function openRcaModal(rowIndex) {{
            const tb = document.getElementById('tracebackFields');
            if (tb) tb.innerHTML = ''
            const modal = document.getElementById("detailModal");
            const rca = allTableData[rowIndex].rca;
            if (!modal || !rca) return;
        
            document.getElementById("modalTitle").textContent = "RCA Details";
            document.getElementById("modalSubtitle").textContent = "";
        
            // Show the query section
            document.querySelector(".modal-left .modal-section").style.display = "block"; 
            document.querySelector(".collapsible-section").style.display = "none";       
            document.querySelector(".modal-right").style.display = "none";               
        
            // Set the query
            document.getElementById("modalQuestion").innerHTML = (allTableData[rowIndex].query || 'N/A').replace(/\\n/g, "<br>");
        
            const container = document.getElementById("metricSheetFields");
            container.innerHTML = "";
        
            const details = rca.details;
            const isArray = Array.isArray(details);
            const dataForTable1 = isArray ? details : (details && Object.keys(details).length > 0 ? [details] : []);
            const dataForTable2 = isArray ? (details.length > 0 ? details[0] : {{}}) : details;
        
            // Define fields for first table
            const failureFields = ['Failure_agent_name', 'Failure Category', 'Agent_spec_fragment', 'Actual_problematic_output', 'Propagation_chain', 'Root cause', 'Span_id'];
            // Define fields for second table
            const loopingFields = ['Looping_agent', 'Loop_count', 'Reason', 'Loop_span_ids'];
            const table1 = document.createElement('table');
            table1.className = 'metric-table';
            const thead1 = document.createElement('thead');
            const trHead1 = document.createElement('tr');
            failureFields.forEach(field => {{
                const th = document.createElement('th');
                th.textContent = field.replace(/_/g, ' ').replace(/\\b\\w/g, l => l.toUpperCase());
                trHead1.appendChild(th);
            }});
            thead1.appendChild(trHead1);
            table1.appendChild(thead1);
        
            const tbody1 = document.createElement('tbody');
            dataForTable1.forEach(item => {{
                const tr = document.createElement('tr');
                failureFields.forEach(field => {{
                    const td = document.createElement('td');
                    td.innerHTML = item[field] ? String(item[field]).replace(/\\n/g, "<br>") : 'N/A';
                    tr.appendChild(td);
                }});
                tbody1.appendChild(tr);
            }});
            table1.appendChild(tbody1);
            container.appendChild(table1);
        
            // Add some spacing
            container.appendChild(document.createElement('br'));
        
            // Create second table for looping details
            const table2 = document.createElement('table');
            table2.className = 'metric-table';
            const thead2 = document.createElement('thead');
            const trHead2 = document.createElement('tr');
            loopingFields.forEach(field => {{
                const th = document.createElement('th');
                th.textContent = field.replace(/_/g, ' ').replace(/\\b\\w/g, l => l.toUpperCase());
                trHead2.appendChild(th);
            }});
            thead2.appendChild(trHead2);
            table2.appendChild(thead2);
        
            const tbody2 = document.createElement('tbody');
            const tr2 = document.createElement('tr');
            loopingFields.forEach(field => {{
                const td = document.createElement('td');
                td.textContent = dataForTable2[field] || 'N/A';
                tr2.appendChild(td);
            }});
            tbody2.appendChild(tr2);
            table2.appendChild(tbody2);
            container.appendChild(table2);
        
            modal.style.display = "block";
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
                    text: score.toFixed(2) + '<br>' + (isPass ? 'PASS' : 'FAIL'),
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
    <script>
    function uploadRuns() {{
        const prevFile = document.getElementById("prevRun").files[0];
        const currFile = document.getElementById("currRun").files[0];
    
        if (!prevFile || !currFile) {{
            alert("Please upload both files");
            return;
        }}
    
        const formData = new FormData();
        formData.append("previous_run", prevFile);
        formData.append("current_run", currFile);
    
        fetch("/compare-runs", {{
            method: "POST",
            body: formData
        }})
        .then(res => res.text())
        .then(html => {{
            const container = document.getElementById("runComparisonResult");
            if (!container) return;
    
            // Insert the returned HTML
            container.innerHTML = html;
    
            // Execute any <script> tags in the returned HTML (browser doesn't run scripts from innerHTML)
            // This creates new script elements so the code runs.
            const scripts = Array.from(container.querySelectorAll("script"));
            scripts.forEach(oldScript => {{
                const newScript = document.createElement("script");
                if (oldScript.src) {{
                    // external script
                    newScript.src = oldScript.src;
                    // ensure scripts execute in order synchronously
                    newScript.async = false;
                }} else {{
                    // inline script
                    newScript.textContent = oldScript.innerHTML;
                }}
                // Append to body to execute, then remove to keep DOM clean
                document.body.appendChild(newScript);
                document.body.removeChild(newScript);
            }});
        }})
        .catch(() => {{
            document.getElementById("runComparisonResult").innerHTML =
                "<b>Error comparing runs</b>";
        }});
    }}
    </script>
    <script>
    let selectedSubs = [];
    
    window.onload = function () {{
        const topicSelect = document.getElementById("topicSelect");
        const dropdown = document.getElementById("subTopicDropdown");
    
        topicSelect.innerHTML = "<option value=''>Select Topic</option>";
    
        [...new Set(DISAGG_DATA.map(d => d.topic))].forEach(t => {{
            topicSelect.innerHTML += `<option value="${{t}}">${{t}}</option>`;
        }});
    
        topicSelect.onchange = () => {{
            selectedSubs = [];
            renderChips();
            dropdown.innerHTML = "";
    
            const topic = topicSelect.value;
            if (!topic) return;
    
            [...new Set(
                DISAGG_DATA.filter(d => d.topic === topic)
                        .map(d => d.sub_topic)
            )].forEach(st => {{
                const div = document.createElement("div");
                div.textContent = st;
                div.onclick = () => addSubTopic(st);
                dropdown.appendChild(div);
            }});
        }};
    
        document.getElementById("subTopicInput").onclick = () => {{
            dropdown.style.display = "block";
        }};
    
        document.addEventListener("click", e => {{
            if (!e.target.closest(".multi-select")) {{
                dropdown.style.display = "none";
            }}
        }});
    }};
    
    function addSubTopic(sub) {{
        if (!selectedSubs.includes(sub)) {{
            selectedSubs.push(sub);
            renderChips();
        }}
    }}
    
    function removeSub(sub) {{
        selectedSubs = selectedSubs.filter(s => s !== sub);
        renderChips();
    }}
    
    function renderChips() {{
        const chipBox = document.getElementById("selectedSubTopics");
        chipBox.innerHTML = "";
    
        selectedSubs.forEach(sub => {{
            const chip = document.createElement("div");
            chip.className = "chip";
            chip.innerHTML = `${{sub}} <span onclick="removeSub('${{sub}}')">×</span>`;
            chipBox.appendChild(chip);
        }});
    
        updateChart();
    }}
    
    function updateChart() {{
        const topic = document.getElementById("topicSelect").value;
        if (!topic || selectedSubs.length === 0) return;
    
        const rows = DISAGG_DATA.filter(
            d => d.topic === topic && selectedSubs.includes(d.sub_topic)
        );
    
        const metrics = {{}};
    
        rows.forEach(r => {{
            Object.entries(r.metrics).forEach(([m, v]) => {{
                if (!metrics[m]) {{
                    metrics[m] = {{ total:0, passed:0, failed:0, scoreSum:0, scoreCount: 0 }};
                }}
                metrics[m].total += v.total;
                metrics[m].passed += v.passed;
                metrics[m].failed += v.failed;
                if(v.aggregate_score !== null && v.aggregate_score !== undefined) {{
                    metrics[m].scoreSum += v.aggregate_score;
                    metrics[m].scoreCount += 1;
                }}
            }});
        }});
    
        const labels = Object.keys(metrics);
        const maxCount = Math.max(
            ...labels.map(m =>
                Math.max(
                    metrics[m].total,
                    metrics[m].passed,
                    metrics[m].failed
                )
            )
        )
    
        Plotly.newPlot("disaggChart", [
            {{
                x: labels,
                y: labels.map(m => metrics[m].total),
                name: "Total",
                type: "bar",
                marker: {{ color: "#1f77b4" }} 
            }},
            {{
                x: labels,
                y: labels.map(m => metrics[m].passed),
                name: "Passed",
                type: "bar",
                marker: {{ color: "#2ca02c" }}
            }},
            {{
                x: labels,
                y: labels.map(m => metrics[m].failed),
                name: "Failed",
                type: "bar",
                marker: {{ color: "#d62728" }}
            }}
        ], {{
            barmode: "group",
            title: `${{topic}} → ${{selectedSubs.join(", ")}}`,
            yaxis: {{ title: "Count",
                      range: [0, maxCount],
                      tickmode: "linear",
                      dtick: 1,
                      showgrid: true,
                      zeroline: true
                    }},
            yaxis2: {{
                title: "Aggregated Score",
                overlaying: "y",
                side: "right",
                range: [0,1],
                tickmode: "linear",
                dtick: 1 / maxCount,
                showgrid: false
            }}
        }});
    }}
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
        • Details DataFrame: 'query', 'response', metric score columns<br>
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
        input_file_path = 'Metrics_template.xlsx'
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
            file_path = "report.html"
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            
            print("HTML length:", len(html_content))
            print("Report saved at:", Path(file_path).resolve())
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
        
        return html_content
        
    except Exception as e:
        print(f"❌ Error generating demo report: {e}")
        return None

app = Flask(__name__)

@app.route("/")
def demo_report():
    return demo_report_generation()
 
@app.route("/compare-runs", methods=["POST"])
def compare_runs():
    try:
        prev_file = request.files.get("previous_run")
        curr_file = request.files.get("current_run")
 
        if not prev_file or not curr_file:
            return "<div class='text-center'><b>Upload both files</b></div>"
 
        prev_df = pd.read_excel(prev_file)
        curr_df = pd.read_excel(curr_file)
 
        generator = ReportGenerator()
        theme = generator.config["theme"]
 
        return generator._create_run_comparison_chart(prev_df, curr_df, theme)
 
    except Exception as e:
        return f"<div class='text-center'><b>Error: {e}</b></div>"

if __name__ == "__main__":
    # demo_report_generation()
    app.run(debug=True)