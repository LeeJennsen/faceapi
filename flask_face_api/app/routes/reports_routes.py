from flask import request, make_response
from flask_restx import Namespace, Resource
from app.db.mongo import db
from fpdf import FPDF
from datetime import datetime
from app.services.jwt_service import verify_token
from functools import wraps
from loguru import logger
import json
from collections import Counter
import pandas as pd
import numpy as np

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import seaborn as sns
    import io
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

api = Namespace('reports', description='Report generation operations')

# --- Helper Functions (Data Processing) ---

def get_all_detections(filters):
    mongo_data = list(db.face_data.find({}))
    all_detections = []
    for doc in mongo_data:
        for det in doc.get("detections", []):
            all_detections.append({
                **det,
                "timestamp": det.get("timestamp") or doc.get("start_timestamp"),
                "camera_id": doc.get("camera_id", "N/A"),
                "device_id": doc.get("device_id", "N/A")
            })
    if not filters:
        return all_detections
    
    def filter_detection(d):
        if not d.get('timestamp'): return False
        try:
            detection_date = datetime.fromisoformat(d['timestamp'].replace('Z', ''))
            if filters.get('year') and str(detection_date.year) != filters['year']: return False
            if filters.get('month'):
                month_val = filters['month'].split('-')[1]
                if str(detection_date.month).zfill(2) != month_val.zfill(2): return False
            if filters.get('date') and detection_date.strftime('%Y-%m-%d') != filters['date']: return False
            if filters.get('device') and d.get('device_id') != filters['device']: return False
            if filters.get('camera') and d.get('camera_id') != filters['camera']: return False
            return True
        except (ValueError, TypeError): return False
    return [d for d in all_detections if filter_detection(d)]

def calculate_summary_stats(detections):
    if not detections:
        return {
            'Total Visits': 0, 'Unique Visitors': 0, 'Avg Attention (s)': 0, 'Avg LOS (s)': 0,
            'Avg Confidence': 0, 'Avg Quality': 0, 'Top Emotion': 'N/A', 'Peak Hour': 'N/A'
        }
    attention_times = [d['attention_time'] for d in detections if isinstance(d.get('attention_time'), (int, float))]
    los_times = [d['length_of_stay'] for d in detections if isinstance(d.get('length_of_stay'), (int, float))]
    confidences = [d['confidence'] for d in detections if isinstance(d.get('confidence'), (int, float))]
    qualities = [d['face_quality_score'] for d in detections if isinstance(d.get('face_quality_score'), (int, float))]
    emotions = [d.get('emotion', 'Unknown') for d in detections if d.get('emotion')]
    top_emotion = Counter(emotions).most_common(1)[0][0] if emotions else 'N/A'
    peak_hour_str = 'N/A'
    if detections:
        hourly_counts = [0] * 24
        for d in detections:
            if d.get('timestamp'):
                try:
                    dt = datetime.fromisoformat(d['timestamp'].replace('Z', ''))
                    hourly_counts[dt.hour] += 1
                except (ValueError, TypeError): continue
        if any(hourly_counts):
            peak_hour = hourly_counts.index(max(hourly_counts))
            peak_hour_str = f"{peak_hour}:00"
    return {
        'Total Visits': len(detections),
        'Unique Visitors': len(set(d.get('track_id') for d in detections if d.get('track_id'))),
        'Avg Attention (s)': f"{(sum(attention_times) / len(attention_times) if attention_times else 0):.2f}",
        'Avg LOS (s)': f"{(sum(los_times) / len(los_times) if los_times else 0):.2f}",
        'Avg Confidence': f"{(sum(confidences) / len(confidences) if confidences else 0):.2f}",
        'Avg Quality': f"{(sum(qualities) / len(qualities) if qualities else 0):.2f}",
        'Top Emotion': top_emotion, 'Peak Hour': peak_hour_str
    }

def count_by_property(detections, prop):
    if not detections: return []
    if prop == 'gender':
        counts = Counter(str(d.get('gender', 'Unknown')).lower() for d in detections)
        return sorted({'Male': counts.get('male', 0) + counts.get('m', 0), 'Female': counts.get('female', 0) + counts.get('f', 0), 'Unknown': counts.get('unknown', 0)}.items(), key=lambda item: item[1], reverse=True)
    counts = Counter(d.get(prop, 'Unknown') for d in detections)
    return sorted(counts.items(), key=lambda item: item[1], reverse=True)

def get_camera_performance_data(detections):
    if not detections: return []
    camera_stats = {}
    for d in detections:
        cam_id = d.get('camera_id', 'Unknown Camera')
        if cam_id not in camera_stats: camera_stats[cam_id] = {'count': 0, 'attention': [], 'stay': []}
        camera_stats[cam_id]['count'] += 1
        if isinstance(d.get('attention_time'), (int, float)): camera_stats[cam_id]['attention'].append(d['attention_time'])
        if isinstance(d.get('length_of_stay'), (int, float)): camera_stats[cam_id]['stay'].append(d['length_of_stay'])
    table_data = []
    for cam_id, data in camera_stats.items():
        avg_att = sum(data['attention']) / len(data['attention']) if data['attention'] else 0
        avg_stay = sum(data['stay']) / len(data['stay']) if data['stay'] else 0
        table_data.append([cam_id, data['count'], f"{avg_att:.1f}s", f"{avg_stay:.1f}s"])
    return sorted(table_data, key=lambda row: row[1], reverse=True)

def get_descriptive_stats(data, name):
    """Helper to calculate descriptive statistics for a list of numbers."""
    if not data or not all(isinstance(x, (int, float)) for x in data):
        return [[f'{name} Count', 0], [f'{name} Mean', 0], [f'{name} Std Dev', 0], [f'{name} Min', 0], [f'{name} Max', 0]]
    arr = np.array(data)
    return [
        [f'{name} Count', len(arr)],
        [f'{name} Mean', f"{np.mean(arr):.2f}"],
        [f'{name} Std Dev', f"{np.std(arr):.2f}"],
        [f'{name} Min', f"{np.min(arr):.2f}"],
        [f'{name} Max', f"{np.max(arr):.2f}"]
    ]

# --- Charting Functions ---
def create_chart_base(fig_size=(6, 4)):
    fig, ax = plt.subplots(figsize=fig_size)
    plt.style.use('seaborn-v0_8-darkgrid')
    plt.rcParams.update({'font.family': 'sans-serif', 'figure.autolayout': True})
    return fig, ax

def save_chart_to_buffer(fig):
    img_buffer = io.BytesIO()
    fig.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight')
    img_buffer.seek(0)
    plt.close(fig)
    return img_buffer

def create_pie_chart(data, title):
    if not MATPLOTLIB_AVAILABLE or not data: return None
    labels, values = zip(*data)
    fig, ax = create_chart_base(fig_size=(5, 5))
    colors = ['#58a6ff', '#db61a2', '#3fb950', '#a371f7', '#f77828', '#39c5cf']
    ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90, colors=colors[:len(labels)], wedgeprops=dict(width=0.4, edgecolor='w'), pctdistance=0.8)
    ax.set_title(title, fontsize=14, weight='bold')
    ax.axis('equal')
    return save_chart_to_buffer(fig)

def create_bar_chart(data, title, xlabel, ylabel, is_horizontal=True):
    if not MATPLOTLIB_AVAILABLE or not data: return None
    labels, values = zip(*data)
    fig, ax = create_chart_base(fig_size=(7, 5))
    if is_horizontal:
        bars = ax.barh(labels, values, color='#58a6ff')
        ax.invert_yaxis()
        ax.bar_label(bars, padding=3, fmt='%d')
    else:
        bars = ax.bar(labels, values, color='#a371f7')
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    ax.set_title(title, fontsize=14, weight='bold')
    ax.set_xlabel(xlabel); ax.set_ylabel(ylabel)
    return save_chart_to_buffer(fig)

def create_histogram(data, title, xlabel):
    if not MATPLOTLIB_AVAILABLE or not data: return None
    clean_data = [x for x in data if isinstance(x, (int, float))]
    if not clean_data: return None
    fig, ax = create_chart_base(fig_size=(7, 5))
    ax.hist(clean_data, bins=15, color='#3fb950', edgecolor='white')
    ax.set_title(title, fontsize=14, weight='bold')
    ax.set_xlabel(xlabel); ax.set_ylabel('Frequency (Number of Visitors)')
    return save_chart_to_buffer(fig)

def create_trend_chart(detections, report_type, title):
    if not MATPLOTLIB_AVAILABLE or not detections: return None, None
    df = pd.DataFrame(detections)
    df['timestamp'] = pd.to_datetime(df['timestamp'].str.replace('Z', '', regex=False), errors='coerce').dropna()
    if df.empty: return None, None
    time_unit, date_format, xlabel = ('D', '%b %d', "Date") if report_type == 'Monthly' else ('H', '%I %p', "Hour of the Day")
    trend_data = df.set_index('timestamp').resample(time_unit).size()
    fig, ax = create_chart_base(fig_size=(10, 5))
    ax.plot(trend_data.index, trend_data.values, marker='o', linestyle='-', color='#f77828')
    ax.set_title(title, fontsize=14, weight='bold')
    ax.set_xlabel(xlabel); ax.set_ylabel('Total Visitors')
    ax.xaxis.set_major_formatter(mdates.DateFormatter(date_format))
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    return save_chart_to_buffer(fig), trend_data

def create_heatmap_chart(detections, title):
    if not MATPLOTLIB_AVAILABLE or not detections: return None, None
    heatmap_data = np.zeros((7, 24))
    for d in detections:
        if d.get('timestamp'):
            try:
                dt = datetime.fromisoformat(d['timestamp'].replace('Z', ''))
                heatmap_data[dt.weekday()][dt.hour] += 1
            except (ValueError, TypeError): continue
    fig, ax = create_chart_base(fig_size=(12, 5))
    sns.heatmap(heatmap_data, ax=ax, cmap="viridis", linewidths=.5, linecolor='white', annot=True, fmt=".0f", annot_kws={"size": 7})
    ax.set_yticklabels(['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'], rotation=0)
    ax.set_xlabel("Hour of the Day"); ax.set_ylabel("Day of the Week")
    ax.set_title(title, fontsize=14, weight='bold')
    return save_chart_to_buffer(fig), heatmap_data

# --- PDF Class with Robust Table and Layouting ---
class PDF(FPDF):
    def header(self):
        self.set_font('Helvetica', 'B', 15)
        self.cell(0, 10, 'GlueckTech AI Analytics Report', 0, 1, 'C')
        self.set_font('Helvetica', '', 8)
        self.cell(0, 8, f'Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', 0, 1, 'C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    def chapter_title(self, title):
        self.set_x(self.l_margin) # FIX: Explicitly set X to avoid horizontal drift
        self.set_font('Helvetica', 'B', 12)
        self.set_fill_color(220, 220, 220)
        self.cell(0, 10, title, 0, 1, 'L', fill=True)
        self.ln(4)

    def _get_num_lines(self, text, cell_width):
        words = text.split()
        if not words: return 1
        num_lines, current_line = 1, words[0]
        available_width = cell_width - (2 * self.c_margin)
        for word in words[1:]:
            if self.get_string_width(current_line + " " + word) > available_width:
                num_lines += 1; current_line = word
            else: current_line += " " + word
        return num_lines

    def add_table(self, headers, data, col_widths):
        self.set_font('Helvetica', 'B', 9); self.set_fill_color(200, 220, 255); self.set_line_width(0.3); self.set_draw_color(180, 180, 180)
        for i, header in enumerate(headers): self.cell(col_widths[i], 8, str(header), 1, 0, 'C', fill=True)
        self.ln()
        self.set_font('Helvetica', '', 9)
        if not data: self.cell(sum(col_widths), 10, 'No data available.', 1, 1, 'C'); return
        line_height = 6 
        for row_index, row in enumerate(data):
            max_lines = max([self._get_num_lines(str(item), col_widths[i]) for i, item in enumerate(row)] or [1])
            row_height = max_lines * line_height
            if self.get_y() + row_height > self.page_break_trigger: self.add_page(self.cur_orientation)
            fill = row_index % 2 == 0; self.set_fill_color(245, 245, 245) if fill else self.set_fill_color(255, 255, 255)
            start_y, start_x = self.get_y(), self.get_x()
            for i, item in enumerate(row):
                current_x = start_x + sum(col_widths[:i])
                self.set_xy(current_x, start_y)
                self.cell(w=col_widths[i], h=row_height, txt="", border=1, fill=True)
                self.set_xy(current_x + self.c_margin, start_y + (row_height - max_lines * line_height) / 2)
                self.multi_cell(w=col_widths[i] - 2 * self.c_margin, h=line_height, txt=str(item), border=0, align='L', fill=False)
            self.set_y(start_y + row_height)
            
    def add_chart_grid(self, charts):
        if not any(charts): return
        page_width = self.w - self.l_margin - self.r_margin
        chart_width = (page_width / 2) - 5
        row_y, max_row_height = self.get_y(), 0
        for i, chart_buffer in enumerate(charts):
            if not chart_buffer: continue
            col_index = i % 2
            if col_index == 0 and i > 0: row_y += max_row_height + 10; max_row_height = 0
            if row_y + 80 > self.page_break_trigger: self.add_page(self.cur_orientation); row_y = self.get_y(); max_row_height = 0
            x_pos = self.l_margin + col_index * (chart_width + 10)
            self.set_xy(x_pos, row_y)
            y_before_image = self.get_y()
            self.image(chart_buffer, w=chart_width)
            max_row_height = max(max_row_height, self.get_y() - y_before_image)
        self.set_y(row_y + max_row_height + 5)

# --- Token Decorator & API Resource ---
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', ' ').split(' ')[-1]
        if not verify_token(token): return {'message': 'Token is invalid or expired'}, 401
        return f(*args, **kwargs)
    return decorated

@api.route('/download')
class DownloadReport(Resource):
    @api.doc(description="Generate and download a PDF statistics report with charts.")
    @token_required
    def get(self):
        try:
            report_type = request.args.get('type', 'Data')
            filters = json.loads(request.args.get('filters', '{}'))
            logger.info(f"Generating '{report_type}' report with filters: {filters}")
            detections = get_all_detections(filters)
            pdf = PDF()
            pdf.add_page()
            
            # --- Page 1: Overview ---
            pdf.chapter_title(f'{report_type} Report Overview')
            if filters:
                pdf.set_font('Helvetica', 'B', 10); pdf.cell(0, 8, "Filters Applied:", 0, 1)
                pdf.set_font('Helvetica', '', 9)
                pdf.multi_cell(0, 5, '\n'.join([f"  - {k.replace('_', ' ').title()}: {v}" for k, v in filters.items()]))
                pdf.ln(4)
            pdf.chapter_title('Key Metrics')
            pdf.add_table(['Metric', 'Value'], list(calculate_summary_stats(detections).items()), [pdf.w * 0.6, pdf.w * 0.25])

            # --- Page 2: Demographics & Trends ---
            pdf.add_page()
            pdf.chapter_title('Demographics Analysis')
            gender_data = count_by_property(detections, 'gender')
            age_data = count_by_property(detections, 'age')
            emotion_data = count_by_property(detections, 'emotion')
            location_data = count_by_property(detections, 'location')
            pdf.add_table(['Gender', 'Count'], gender_data, [pdf.w * 0.4, pdf.w * 0.45]); pdf.ln(5)
            pdf.add_table(['Age Group', 'Count'], age_data, [pdf.w * 0.4, pdf.w * 0.45]); pdf.ln(5)
            pdf.add_table(['Emotion', 'Count'], emotion_data, [pdf.w * 0.4, pdf.w * 0.45]); pdf.ln(5)
            pdf.add_table(['Location', 'Count'], location_data, [pdf.w * 0.4, pdf.w * 0.45]); pdf.ln(10)
            pdf.add_chart_grid([
                create_pie_chart(gender_data, 'Gender Distribution'), create_pie_chart(age_data, 'Age Group Distribution'),
                create_pie_chart(location_data, 'Location Distribution'), create_bar_chart(emotion_data, 'Emotion Analysis', 'Count', 'Emotion')
            ])
            
            pdf.chapter_title(f'{report_type} Visitor Trend')
            trend_chart, trend_data = create_trend_chart(detections, report_type, f'Visitor Trend')
            if trend_chart:
                trend_list = [[idx.strftime('%Y-%m-%d %H:%M'), val] for idx, val in trend_data.items()]
                pdf.add_table(['Timestamp', 'Visitors'], trend_list, [pdf.w * 0.45, pdf.w * 0.4])
                pdf.ln(5)
                pdf.image(trend_chart, w=pdf.w - pdf.l_margin * 2)

            # --- Page 3: Performance & Heatmap ---
            pdf.add_page()
            pdf.chapter_title('Performance Analysis')
            attention_data = [d.get('attention_time') for d in detections]
            los_data = [d.get('length_of_stay') for d in detections]
            pdf.add_table(['Statistic', 'Value'], get_descriptive_stats(attention_data, 'Attention Time'), [pdf.w * 0.45, pdf.w * 0.4]); pdf.ln(5)
            pdf.add_table(['Statistic', 'Value'], get_descriptive_stats(los_data, 'Length of Stay'), [pdf.w * 0.45, pdf.w * 0.4]); pdf.ln(10)
            pdf.add_chart_grid([
                create_histogram(attention_data, 'Attention Time Distribution', 'Time (seconds)'),
                create_histogram(los_data, 'Length of Stay Distribution', 'Time (seconds)')
            ])

            pdf.chapter_title('Visitor Traffic Heatmap')
            heatmap_chart, heatmap_data = create_heatmap_chart(detections, 'Visitor Traffic Heatmap (Day vs Hour)')
            if heatmap_chart:
                days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
                heatmap_list = [[days[r], h, int(heatmap_data[r, h])] for r in range(7) for h in range(24) if heatmap_data[r, h] > 0]
                pdf.add_table(['Day', 'Hour', 'Visitors'], sorted(heatmap_list, key=lambda x: x[2], reverse=True), [pdf.w*0.3, pdf.w*0.3, pdf.w*0.25])
                pdf.ln(5)
                pdf.image(heatmap_chart, w=pdf.w - pdf.l_margin * 2)

            # --- Page 4: Camera Performance ---
            pdf.add_page()
            pdf.chapter_title('Camera Performance')
            camera_perf_data = get_camera_performance_data(detections)
            pdf.add_table(['Camera ID', 'Visitors', 'Avg. Attention', 'Avg. Stay'], camera_perf_data, [pdf.w * 0.4, pdf.w * 0.15, pdf.w * 0.15, pdf.w * 0.15])
            pdf.ln(5)
            camera_traffic_chart = create_bar_chart([(row[0], row[1]) for row in camera_perf_data], 'Visitor Count by Camera', 'Camera ID', 'Total Visitors', is_horizontal=False)
            if camera_traffic_chart: pdf.image(camera_traffic_chart, w=pdf.w - pdf.l_margin * 2)

            # --- Subsequent Pages: Location Deep Dives ---
            top_locations = [loc[0] for loc in count_by_property(detections, 'location')[:3] if loc[0] != 'Unknown']
            for location in top_locations:
                pdf.add_page()
                pdf.chapter_title(f'Deep Dive: {location}')
                loc_detections = [d for d in detections if d.get('location') == location]
                pdf.add_table(['Metric', 'Value'], list(calculate_summary_stats(loc_detections).items()), [pdf.w * 0.6, pdf.w * 0.25]); pdf.ln(10)
                loc_gender_data = count_by_property(loc_detections, 'gender')
                loc_age_data = count_by_property(loc_detections, 'age')
                pdf.add_table(['Gender', 'Count'], loc_gender_data, [pdf.w * 0.4, pdf.w * 0.45]); pdf.ln(5)
                pdf.add_table(['Age Group', 'Count'], loc_age_data, [pdf.w * 0.4, pdf.w * 0.45]); pdf.ln(10)
                pdf.add_chart_grid([
                    create_pie_chart(loc_gender_data, f'Gender @ {location}'),
                    create_pie_chart(loc_age_data, f'Age @ {location}'),
                ])

            # --- Finalize and Send Response ---
            response = make_response(bytes(pdf.output()))
            response.headers.set('Content-Disposition', f'attachment; filename="{report_type.lower()}_report_{datetime.now().strftime("%Y%m%d")}.pdf"')
            response.headers.set('Content-Type', 'application/pdf')
            return response
            
        except Exception as e:
            logger.error(f"Failed to generate PDF report: {e}", exc_info=True)
            import traceback
            traceback.print_exc()
            return {"message": "Failed to generate report due to an internal server error."}, 500