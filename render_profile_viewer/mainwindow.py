# Copyright 2023-2024 DreamWorks Animation LLC
# SPDX-License-Identifier: Apache-2.0

from PyQt5 import QtWidgets, QtCore, QtChart, QtGui
from PyQt5.QtGui import QImage, QColor, QTextCharFormat
import os
import numpy as np
import OpenImageIO as oiio
import fnmatch
import json
import sys
import shutil
import argparse
import subprocess
import copy
import re
import datetime

try:
    from render_profile_viewer._version import __version__
except ModuleNotFoundError:
    __version__ = 'test'

def load_exr_as_qimage(file_path, gamma=2.2):
    # Open the EXR file
    input_file = oiio.ImageInput.open(file_path)
    if not input_file:
        raise RuntimeError(f"Could not open {file_path}")

    # Read the image data
    spec = input_file.spec()
    image = input_file.read_image()
    input_file.close()

    # Convert the image to numpy array and normalize to 0-255 range
    image_array = np.array(image)

    # Apply gamma correction
    image_array = np.power(image_array, 1/gamma)

    image_array = np.clip(image_array * 255, 0, 255).astype(np.uint8)

    # If the image has an alpha channel, drop it
    if image_array.shape[2] == 4:
        image_array = image_array[:, :, :3]

    # Ensure the array is contiguous in memory
    image_array = np.ascontiguousarray(image_array)

    # Create QImage from the numpy array
    height, width, channels = image_array.shape
    bytes_per_line = channels * width
    q_image = QImage(image_array.tobytes(), width, height, bytes_per_line, QImage.Format_RGB888)

    return (q_image, width, height)

def get_seconds_from_time(time_string):
    hours = float(time_string.split(':')[-3])
    minutes = float(time_string.split(':')[-2])
    seconds = float(time_string.split(':')[-1])
    return seconds + minutes * 60.0 + hours * 3600.0


def get_gigabytes_from_size(size_string, size_unit):
    if size_unit == "GB":
        return float(size_string)
    elif size_unit == "MB":
        return float(size_string) / 1024
    elif size_unit == "KB":
        return float(size_string) / 1024 / 1024


# noinspection PyUnresolvedReferences
class RenderProfileChartView(QtChart.QChartView):

    stat_signal = QtCore.pyqtSignal(str)

    stat_colors = dict()

    stat_colors_values = {
                   # Render prep
                   "Checkout license":                      (50, 50, 50),
                   "Loading scene":                         (50, 50, 80),
                   "Initialize renderer":                   (50, 80, 50),
                   "Generating procedurals":                (80, 50, 50),
                   "Tessellation":                          (120, 120, 50),
                   "Building BVH":                          (120, 50, 50),
                   "Building GPU BVH":                      (50, 50, 120),

                   # Scalar
                   "Render driver overhead":                (118, 130, 201),
                   "Adaptive tree query":                   (75, 100, 200),
                   "Adaptive tree exclusive lock":          (75, 150, 200),
                   "Render driver serial time":             (74, 206, 223),
                   "Integration":                           (245, 121, 111),
                   "Subsurface integration":                (139, 94, 21),
                   "Volume integration":                    (146, 114, 202),
                   "Shading (excl. OIIO)":                  (253, 180, 74),
                   "Texturing (OIIO)":                      (150, 95, 175),
                   "Primary ray generation":                (185, 185, 185),
                   "Init Intersection":                     (171, 211, 126),
                   "Embree intersection rays":              (97, 179, 244),
                   "Embree occlusion rays":                 (253, 209, 78),
                   "Embree volume rays":                    (246, 166, 37),
                   "Compute ray derivatives":               (141, 161, 171),
                   "Adaptive tree rebuild":                 (84, 182, 231),
                   "Add sample handler":                    (88, 91, 113),
                   "AOVs":                                  (160, 84, 78),
                   "MISSING TIME":                          (127, 197, 130),

                   # Vector and GPU Only
                   "RayState allocs":                       (218, 228, 114),
                   "Ray handler (excl. embree)":            (253, 239, 115),
                   "Shade handler (excl. isect+shading)":   (237, 95, 143),
                   "Queuing logic (incl. sorting)":         (74, 179, 169),
                   "Occl query handler (excl. embree)":     (253, 135, 97),
                   "TLS allocs (excl. RayStates)":          (76, 192, 245),
                   "Post integration (SOA->AOS/queuing)":   (183, 101, 197),

                   # GPU Only
                   "GPU occlusion rays":                    (50, 50, 50),
                   # pixel samples
                   "pixel_samples":                         (200, 50, 100),
                   # memory
                   "Geometry memory":                       (100, 200, 50),
                   "BVH memory":                            (50, 100, 200),
                   "MCRT memory":                           (200, 50, 100)}

    improvements_color = QtGui.QColor(0, 200, 0)
    regression_color = QtGui.QColor(200, 0, 0)
    fallback_color = QtGui.QColor(200, 0, 200)
    crash_color = QtGui.QColor(255, 0, 0)
    missing_color = QtGui.QColor(200, 0, 0)
    scalar_color = QtGui.QColor(255, 0, 0)
    vector_color = QtGui.QColor(0, 255, 0)
    xpu_color = QtGui.QColor(0, 0, 255)


    memory_stats = ["Geometry memory",
                    "BVH memory",
                    "MCRT memory"]

    render_prep_stats = ["Checkout license",
                         "Loading scene",
                         "Initialize renderer",
                         "Generating procedurals",
                         "Tessellation",
                         "Building BVH",
                         "Building GPU BVH"]

    scalar_stats = ["Render driver overhead",
                    "Adaptive tree query",
                    "Adaptive tree exclusive lock",
                    "Render driver serial time",
                    "Integration",
                    "Subsurface integration",
                    "Volume integration",
                    "Shading (excl. OIIO)",
                    "Texturing (OIIO)",
                    "Primary ray generation",
                    "Init Intersection",
                    "Embree intersection rays",
                    "Embree occlusion rays",
                    "Embree volume rays",
                    "Compute ray derivatives",
                    "Adaptive tree rebuild",
                    "Add sample handler",
                    "AOVs",
                    "MISSING TIME"]

    vector_stats = ["RayState allocs",
                    "Ray handler (excl. embree)",
                    "Shade handler (excl. isect+shading)",
                    "Queuing logic (incl. sorting)",
                    "Occl query handler (excl. embree)",
                    "TLS allocs (excl. RayStates)",
                    "Post integration (SOA->AOS/queuing)"]

    xpu_stats = ["GPU occlusion rays"]

    def __init__(self):
        super().__init__()

        self.stat_colors.clear()
        for stat_name in self.stat_colors_values.keys():
            stat_color = QtGui.QColor(int(self.stat_colors_values[stat_name][0]),
                                      int(self.stat_colors_values[stat_name][1]),
                                      int(self.stat_colors_values[stat_name][2]))
            self.stat_colors[stat_name] = stat_color

        self.series = QtChart.QStackedBarSeries()

        self.setRenderHint(QtGui.QPainter.Antialiasing)

        self.max_y = 0.0

    def keyPressEvent(self, event):
        keymap = {
            QtCore.Qt.Key_Up: lambda: self.chart().scroll(0, 20),
            QtCore.Qt.Key_W: lambda: self.chart().scroll(0, 20),
            QtCore.Qt.Key_Down: lambda: self.chart().scroll(0, -20),
            QtCore.Qt.Key_S: lambda: self.chart().scroll(0, -20),
            QtCore.Qt.Key_Right: lambda: self.chart().scroll(20, 0),
            QtCore.Qt.Key_D: lambda: self.chart().scroll(20, 0),
            QtCore.Qt.Key_Left: lambda: self.chart().scroll(-20, 0),
            QtCore.Qt.Key_A: lambda: self.chart().scroll(-20, 0),
            QtCore.Qt.Key_Equal: self.chart().zoomIn,
            QtCore.Qt.Key_E: self.chart().zoomIn,
            QtCore.Qt.Key_Minus: self.chart().zoomOut,
            QtCore.Qt.Key_Q: self.chart().zoomOut,
            QtCore.Qt.Key_Home: self.chart().zoomReset,
            QtCore.Qt.Key_R: self.chart().zoomReset
        }
        callback = keymap.get(event.key())
        if callback:
            callback()

    def hover_bar_series(self, status, index, barset):
        if status:
            host_name = barset.property('host_name')

            pixel_samples = 0.0
            pixel_samples_list = barset.property('pixel_samples')
            if pixel_samples_list and index < len(pixel_samples_list):
                pixel_samples = pixel_samples_list[index]

            visible_time = 0.0
            visible_time_list = barset.property('visible_time')
            if visible_time_list and index < len(visible_time_list):
                visible_time = visible_time_list[index]

            total_render_prep_time = 0.0
            total_render_prep_time_list = barset.property('total_render_prep_time')
            if total_render_prep_time_list and index < len(total_render_prep_time_list):
                total_render_prep_time = total_render_prep_time_list[index]

            total_mcrt_time = 0.0
            total_mcrt_time_list = barset.property('total_mcrt_time')
            if total_mcrt_time_list and index < (len(total_mcrt_time_list)):
                total_mcrt_time = total_mcrt_time_list[index]

            total_time = total_render_prep_time + total_mcrt_time

            visible_time = '%0.2fs' % visible_time
            total_render_prep_time = '%0.2fs' % total_render_prep_time
            total_mcrt_time = '%0.2fs' % total_mcrt_time
            total_time = '%0.2fs' % total_time

            self.stat_signal.emit(f"{barset.label()}={barset.at(index)}    "
                                  f"visible time={visible_time}    "
                                  f"total render prep time={total_render_prep_time}    "
                                  f"total MCRT time={total_mcrt_time}    "
                                  f"total time={total_time}    "
                                  f"test pixel samples={pixel_samples}    "
                                  f"host_name = {host_name[index]}")
        else:
            self.stat_signal.emit("")

    @staticmethod
    def get_stat(stats_dict, extra_stats_dict, stat_name, test_type, week):
        stat_value = 0
        if stats_dict[week][test_type]:
            if stat_name in stats_dict[week][test_type]:
                stat_value = stats_dict[week][test_type][stat_name]
            for extra_stat in extra_stats_dict.keys():
                if stats_dict[week][test_type] == "missing":
                    extra_stats_dict[extra_stat].append(0)
                elif extra_stat in stats_dict[week][test_type]:
                    extra_stats_dict[extra_stat].append(stats_dict[week][test_type][extra_stat])
        return stat_value

    def process_test_type_for_week(self,
                                   test_type,
                                   week, week_index,
                                   stat_name, stats_dict, prev_stats_dict, extra_stats_dict,
                                   show_regressions, show_improvements,
                                   regressions_threshold, improvements_threshold,
                                   main_bar_set, regressions_bar_set,
                                   improvements_bar_set,
                                   fallback_bar_set, fallback,
                                   crash_bar_set, crash,
                                   missing_bar_set, missing):

        stat = self.get_stat(stats_dict, extra_stats_dict, stat_name, test_type, week)
        if week_index > 0 and prev_stats_dict[test_type] != 0 and (show_regressions or show_improvements):
            stat_ratio = stat / prev_stats_dict[test_type]
            if missing:
                missing_bar_set.append(0)
                fallback_bar_set.append(0)
                crash_bar_set.append(0)
                main_bar_set.append(0)
                improvements_bar_set.append(0)
                regressions_bar_set.append(0)
            elif fallback:
                missing_bar_set.append(0)
                fallback_bar_set.append(stat)
                crash_bar_set.append(0)
                main_bar_set.append(0)
                improvements_bar_set.append(0)
                regressions_bar_set.append(0)
            elif crash:
                missing_bar_set.append(0)
                fallback_bar_set.append(0)
                crash_bar_set.append(stat)
                main_bar_set.append(0)
                improvements_bar_set.append(0)
                regressions_bar_set.append(0)
            elif stat_ratio > regressions_threshold and show_regressions:
                missing_bar_set.append(0)
                fallback_bar_set.append(0)
                crash_bar_set.append(0)
                main_bar_set.append(0)
                improvements_bar_set.append(0)
                regressions_bar_set.append(stat)
            elif stat_ratio < improvements_threshold and show_improvements:
                missing_bar_set.append(0)
                fallback_bar_set.append(0)
                crash_bar_set.append(0)
                main_bar_set.append(0)
                improvements_bar_set.append(stat)
                regressions_bar_set.append(0)
            else:
                missing_bar_set.append(0)
                fallback_bar_set.append(0)
                crash_bar_set.append(0)
                main_bar_set.append(stat)
                improvements_bar_set.append(0)
                regressions_bar_set.append(0)
        else:
            if missing:
                missing_bar_set.append(0)
                fallback_bar_set.append(0)
                crash_bar_set.append(0)
                main_bar_set.append(0)
                improvements_bar_set.append(0)
                regressions_bar_set.append(0)
            elif fallback:
                missing_bar_set.append(0)
                fallback_bar_set.append(stat)
                crash_bar_set.append(0)
                main_bar_set.append(0)
                improvements_bar_set.append(0)
                regressions_bar_set.append(0)
            elif crash:
                missing_bar_set.append(0)
                fallback_bar_set.append(0)
                crash_bar_set.append(stat)
                main_bar_set.append(0)
                improvements_bar_set.append(0)
                regressions_bar_set.append(0)
            else:
                missing_bar_set.append(0)
                fallback_bar_set.append(0)
                crash_bar_set.append(0)
                main_bar_set.append(stat)
                improvements_bar_set.append(0)
                regressions_bar_set.append(0)
        prev_stats_dict[test_type] = stat

    def add_line_series(self,
                        chart,
                        x_axis,
                        y_axis,
                        stats_dict,
                        type_visibility_list):
        scalar_pen = QtGui.QPen()
        scalar_pen.setWidth(3)
        scalar_pen.setColor(self.scalar_color)
        scalar_line_series = QtChart.QLineSeries()
        scalar_line_series.setPen(scalar_pen)

        vector_pen = QtGui.QPen()
        vector_pen.setWidth(3)
        vector_pen.setColor(self.vector_color)
        vector_line_series = QtChart.QLineSeries()
        vector_line_series.setPen(vector_pen)

        xpu_pen = QtGui.QPen()
        xpu_pen.setWidth(3)
        xpu_pen.setColor(self.xpu_color)
        xpu_line_series = QtChart.QLineSeries()
        xpu_line_series.setPen(xpu_pen)

        x = 0
        for week_index, week in enumerate(stats_dict.keys()):
            for test_type in ['scalar', 'vector', 'xpu']:
                if test_type in stats_dict[week] and \
                   stats_dict[week][test_type] and \
                   test_type in type_visibility_list:

                    if stats_dict[week][test_type] == "missing":
                        visible_time = 0
                    else:
                        visible_time = float(stats_dict[week][test_type]['visible_time'])

                    if test_type == 'scalar':
                        scalar_line_series.append(x, visible_time)
                    if test_type == 'vector':
                        vector_line_series.append(x, visible_time)
                    if test_type == 'xpu':
                        xpu_line_series.append(x, visible_time)
                    x += 1
        chart.addSeries(scalar_line_series)
        chart.addSeries(vector_line_series)
        chart.addSeries(xpu_line_series)

        scalar_line_series.attachAxis(x_axis)
        scalar_line_series.attachAxis(y_axis)
        vector_line_series.attachAxis(x_axis)
        vector_line_series.attachAxis(y_axis)
        xpu_line_series.attachAxis(x_axis)
        xpu_line_series.attachAxis(y_axis)

    @staticmethod
    def check_host_type(stats_dict, week, test_type, host_visibility_list):
        if len(host_visibility_list) == 0:
            return True

        if 'host_name' not in stats_dict[week][test_type]:
            return True

        host_name = stats_dict[week][test_type]['host_name']

        for host_type in host_visibility_list:
            if host_name.startswith(host_type):
                return True

        return False

    def update_chart(self,
                     test_name,
                     stats_dict,
                     show_pixel_samples=False,
                     show_memory=False,
                     show_host_names=False,
                     type_visibility_list=None,
                     host_visibility_list=None,
                     stat_visibility_list=None,
                     resize=False,
                     font_size=11,
                     show_regressions=False,
                     regressions_threshold=110.0,
                     show_improvements=False,
                     improvements_threshold=90.0,
                     dark_theme=False,
                     show_line_series=False,
                     divide_by_ps=False,
                     show_fallback=False,
                     show_crash=False,
                     label_angle=90):

        regressions_threshold = (100.0 + regressions_threshold) / 100.0
        improvements_threshold = (100.0 - improvements_threshold) / 100.0

        chart = QtChart.QChart()
        chart.setTitle(test_name)

        if dark_theme:
            chart.setTheme(QtChart.QChart.ChartThemeDark)

        title_font = chart.titleFont()
        title_font.setPointSize(font_size)
        chart.setTitleFont(title_font)
        self.setChart(chart)

        if len(stats_dict) == 0:
            return

        stacked_bar_series = QtChart.QStackedBarSeries()
        stacked_bar_series.hovered.connect(self.hover_bar_series)

        if show_pixel_samples:
            stat_names = ['pixel_samples']
        else:
            stat_names = self.stat_colors.keys()

        categories = list()
        for stat_name in stat_names:
           if not stat_visibility_list or (not show_pixel_samples and stat_name not in stat_visibility_list):
                continue

           main_bar_set = QtChart.QBarSet(stat_name)
           if stat_name in self.stat_colors:
               main_bar_set.setColor(self.stat_colors[stat_name])

           regressions_bar_set = QtChart.QBarSet(stat_name)
           if stat_name in self.stat_colors:
               regressions_bar_set.setColor(self.stat_colors[stat_name])
           overlay_pen = regressions_bar_set.pen()
           overlay_pen.setWidth(5)
           overlay_pen.setColor(self.regression_color)
           regressions_bar_set.setPen(overlay_pen)

           improvements_bar_set = QtChart.QBarSet(stat_name)
           if stat_name in self.stat_colors:
               improvements_bar_set.setColor(self.stat_colors[stat_name])
           overlay_pen = improvements_bar_set.pen()
           overlay_pen.setWidth(5)
           overlay_pen.setColor(self.improvements_color)
           improvements_bar_set.setPen(overlay_pen)

           fallback_bar_set = QtChart.QBarSet(stat_name)
           if stat_name in self.stat_colors:
               fallback_bar_set.setColor(self.stat_colors[stat_name])
           overlay_pen = fallback_bar_set.pen()
           overlay_pen.setWidth(5)
           overlay_pen.setColor(self.fallback_color)
           fallback_bar_set.setPen(overlay_pen)

           crash_bar_set = QtChart.QBarSet(stat_name)
           if stat_name in self.stat_colors:
               crash_bar_set.setColor(self.stat_colors[stat_name])
           overlay_pen = crash_bar_set.pen()
           overlay_pen.setWidth(5)
           overlay_pen.setColor(self.crash_color)
           crash_bar_set.setPen(overlay_pen)

           missing_bar_set = QtChart.QBarSet(stat_name)
           if stat_name in self.stat_colors:
               missing_bar_set.setColor(self.stat_colors[stat_name])

           extra_stats_dict = dict()
           extra_stats_dict['visible_time'] = list()
           extra_stats_dict['total_render_prep_time'] = list()
           extra_stats_dict['total_mcrt_time'] = list()
           extra_stats_dict['pixel_samples'] = list()
           extra_stats_dict['host_name'] = list()

           prev_stats_dict = dict()
           prev_stats_dict['scalar'] = 0
           prev_stats_dict['vector'] = 0
           prev_stats_dict['xpu'] = 0

           for week_index, week in enumerate(stats_dict.keys()):
               for test_type in ['scalar', 'vector', 'xpu']:
                   if test_type in stats_dict[week] and test_type in type_visibility_list:

                       if not stats_dict[week][test_type]:
                           continue

                       # Check for missing week
                       missing = False
                       if stats_dict[week][test_type] == "missing":
                           missing = True

                       # Check for host type
                       if not self.check_host_type(stats_dict, week, test_type, host_visibility_list):
                           continue

                       # Categories (bottom of chart)
                       if missing:
                           categories.append(f"MISSING! - {week} ({test_type})")
                       elif show_host_names:
                           host_name = 'Unknown'
                           if 'host_name' in stats_dict[week][test_type]:
                               host_name = stats_dict[week][test_type]['host_name'].split('.')[0]
                           if show_fallback and \
                              'fallback' in stats_dict[week][test_type] and \
                              'fallback_mode' in stats_dict[week][test_type]:

                               categories.append(f"{host_name}: {week} "
                                                 f"({test_type} -> {stats_dict[week][test_type]['fallback_mode']})")
                           else:
                               categories.append(f"{host_name}: {week} ({test_type})")
                       else:
                           if show_fallback and \
                              'fallback' in stats_dict[week][test_type] and \
                              'fallback_mode' in stats_dict[week][test_type]:

                               categories.append(f"{week} "
                                                 f"({test_type} -> {stats_dict[week][test_type]['fallback_mode']})")
                           else:
                               categories.append(f"{week} ({test_type})")

                       # Check for fallback
                       fallback = False
                       if show_fallback and 'fallback' in stats_dict[week][test_type]:
                           fallback = stats_dict[week][test_type]['fallback']

                       # Check for crash
                       crash = False
                       if show_crash and 'crash' in stats_dict[week][test_type]:
                           crash = stats_dict[week][test_type]['crash']

                       self.process_test_type_for_week(test_type,
                                                       week, week_index,
                                                       stat_name, stats_dict, prev_stats_dict, extra_stats_dict,
                                                       show_regressions, show_improvements,
                                                       regressions_threshold, improvements_threshold,
                                                       main_bar_set, regressions_bar_set, improvements_bar_set,
                                                       fallback_bar_set, fallback,
                                                       crash_bar_set, crash,
                                                       missing_bar_set, missing)

           for bar_set in [main_bar_set, regressions_bar_set, improvements_bar_set, fallback_bar_set, crash_bar_set, missing_bar_set]:
               for extra_stat in extra_stats_dict:
                   bar_set.setProperty(extra_stat, extra_stats_dict[extra_stat])
               stacked_bar_series.append(bar_set)

        chart.addSeries(stacked_bar_series)

        x_axis = QtChart.QBarCategoryAxis()
        x_axis.append(categories)
        x_axis.setLabelsAngle(label_angle)
        if show_host_names:
            x_axis.setTitleText("Host: Date (Type)")
        else:
            x_axis.setTitleText("Date (Type)")
        title_font = x_axis.titleFont()
        title_font.setPointSize(font_size)
        x_axis.setTitleFont(title_font)
        labels_font = x_axis.labelsFont()
        labels_font.setPointSize(int(font_size * 0.75))
        x_axis.setLabelsFont(labels_font)
        chart.addAxis(x_axis, QtCore.Qt.AlignBottom)
        stacked_bar_series.attachAxis(x_axis)

        y_axis = QtChart.QValueAxis()
        if divide_by_ps:
            y_axis.setTitleText("Time per pixel sample (seconds)")
        elif show_pixel_samples:
            y_axis.setTitleText("Pixel Samples (millions)")
        elif show_memory:
            y_axis.setTitleText("Memory (GB)")
        else:
            y_axis.setTitleText("Time (seconds)")
        labels_font = y_axis.labelsFont()
        labels_font.setPointSize(font_size)
        y_axis.setLabelsFont(labels_font)
        title_font = y_axis.titleFont()
        title_font.setPointSize(font_size)
        y_axis.setTitleFont(title_font)
        chart.addAxis(y_axis, QtCore.Qt.AlignLeft)
        stacked_bar_series.attachAxis(y_axis)

        if not resize:
            # Set the saved size
            y_axis.setMax(self.max_y)
        self.max_y = y_axis.max()

        chart.legend().setVisible(False)

        if show_line_series:
            self.add_line_series(chart,
                                 x_axis,
                                 y_axis,
                                 stats_dict,
                                 type_visibility_list)


# noinspection PyUnresolvedReferences
class MyWindow(QtWidgets.QMainWindow):
    def __init__(self, logs):
        super().__init__()

        self.images_cache = dict()
        self.log_file_mode = False
        if logs:
            self.log_files = logs
            self.log_file_mode = True

        self.setGeometry(200, 200, 1300, 800)

        # TODO Remove these hard coded directories - ask user on first run
        self.profile_directory = "/rel/ci_builds/Moonbase/ProfileRuns/latest_results/profile_reports"
        self.process_weeks = True

        self.work_directory = os.path.join(os.environ["HOME"], "render_profile_viewer")
        if not os.path.exists(self.work_directory):
            os.makedirs(self.work_directory)

        self.cache_directory = os.path.join(self.work_directory, "cache")
        if not os.path.exists(self.cache_directory):
            os.makedirs(self.cache_directory)

        if self.log_file_mode:
            self.use_cache = False
        else:
            self.use_cache = True

        self.setWindowTitle(f"Render Profile Viewer {__version__} -- (Profile directory: {self.profile_directory})")

        # Stats filled in clicked_weeks_list and passed to RenderProfileChartView
        self.stats = dict()

        # Height for test types and other options group box UI
        group_box_height = 100

        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)

        main_v_layout = QtWidgets.QVBoxLayout()
        central_widget.setLayout(main_v_layout)

        # Menus
        menu_bar = self.menuBar()
        menu_bar.setNativeMenuBar(False)

        # File Menu
        file_menu = menu_bar.addMenu('File')

        set_profile_dir_action = QtWidgets.QAction("Set profile dir", self)
        set_profile_dir_action.triggered.connect(self.set_profile_dir)
        file_menu.addAction(set_profile_dir_action)

        use_cache_action = QtWidgets.QAction("Use cache", self)
        use_cache_action.setCheckable(True)
        use_cache_action.setChecked(self.use_cache)
        use_cache_action.triggered.connect(self.set_use_cache)
        file_menu.addAction(use_cache_action)

        set_cache_dir_action = QtWidgets.QAction("Set cache dir", self)
        set_cache_dir_action.triggered.connect(self.set_cache_dir)
        file_menu.addAction(set_cache_dir_action)

        clear_cache_dir_action = QtWidgets.QAction("Clear cache dir", self)
        clear_cache_dir_action.triggered.connect(self.clear_cache_dir)
        file_menu.addAction(clear_cache_dir_action)

        quit_action = QtWidgets.QAction("Quit", self)
        quit_action.triggered.connect(QtCore.QCoreApplication.quit)
        file_menu.addAction(quit_action)

        # View Menu
        view_menu = menu_bar.addMenu('View')

        set_light_theme_action = QtWidgets.QAction("Set light theme", self)
        set_light_theme_action.triggered.connect(self.set_light_theme)
        view_menu.addAction(set_light_theme_action)

        set_dark_theme_action = QtWidgets.QAction("Set dark theme", self)
        set_dark_theme_action.triggered.connect(self.set_dark_theme)
        view_menu.addAction(set_dark_theme_action)

        increase_font_size_action = QtWidgets.QAction("Increase font size", self)
        increase_font_size_action.triggered.connect(self.font_size_increase)
        view_menu.addAction(increase_font_size_action)

        decrease_font_size_action = QtWidgets.QAction("Decrease font size", self)
        decrease_font_size_action.triggered.connect(self.font_size_decrease)
        view_menu.addAction(decrease_font_size_action)

        set_label_angle_action = QtWidgets.QAction("Set chart label angle", self)
        set_label_angle_action.triggered.connect(self.set_chart_label_angle)
        view_menu.addAction(set_label_angle_action)

        main_h_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        main_h_splitter.setHandleWidth(10)
        main_v_layout.addWidget(main_h_splitter)

        # Theme
        self.use_dark_theme = True

        tests_weeks_log_widget = QtWidgets.QWidget()
        main_h_splitter.addWidget(tests_weeks_log_widget)
        tests_weeks_log_widget.setLayout(QtWidgets.QVBoxLayout())

        if self.log_file_mode:
            # Log List
            logs_list_label = QtWidgets.QLabel("Logs")
            tests_weeks_log_widget.layout().addWidget(logs_list_label)
            self.show_full_paths_checkbox = QtWidgets.QCheckBox("Show full paths")
            self.show_full_paths_checkbox.stateChanged.connect(self.checkbox_changed_full_paths)
            tests_weeks_log_widget.layout().addWidget(self.show_full_paths_checkbox)
            self.logs_list = QtWidgets.QListWidget()
            self.logs_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
            tests_weeks_log_widget.layout().addWidget(self.logs_list)
            self.logs_list.itemSelectionChanged.connect(self.selection_changed_logs)
            self.populate_logs_list()
            self.logs_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            self.logs_list.customContextMenuRequested.connect(self.log_list_context_menu)
        else:
            tests_weeks_v_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
            tests_weeks_v_splitter.setHandleWidth(10)
            tests_weeks_log_widget.layout().addWidget(tests_weeks_v_splitter)

            # Test List
            tests_list_widget = QtWidgets.QWidget()
            tests_weeks_v_splitter.addWidget(tests_list_widget)
            tests_list_widget.setLayout(QtWidgets.QVBoxLayout())
            tests_list_label = QtWidgets.QLabel("Tests")
            tests_list_widget.layout().addWidget(tests_list_label)
            self.tests_list = QtWidgets.QListWidget()
            tests_list_widget.layout().addWidget(self.tests_list)
            self.tests_list.itemSelectionChanged.connect(self.selection_changed_tests)
            self.populate_test_list()

            # Weeks List
            weeks_list_widget = QtWidgets.QWidget()
            tests_weeks_v_splitter.addWidget(weeks_list_widget)
            weeks_list_widget.setLayout(QtWidgets.QVBoxLayout())
            weeks_list_label = QtWidgets.QLabel("Weeks")
            weeks_list_widget.layout().addWidget(weeks_list_label)
            self.weeks_list = QtWidgets.QListWidget()
            weeks_list_widget.layout().addWidget(self.weeks_list)
            self.weeks_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
            self.weeks_list.itemSelectionChanged.connect(self.selection_changed_weeks)

        # Chart / Image / Log tab widget
        self.chart_image_log_tab_widget = QtWidgets.QTabWidget()
        self.chart_image_log_tab_widget.setAutoFillBackground(True)
        main_h_splitter.addWidget(self.chart_image_log_tab_widget)

        # Create chart
        self.render_profile_chart = RenderProfileChartView()
        self.render_profile_chart.stat_signal.connect(self.statusBar().showMessage)

        self.chart_label_angle = 90

        # Chart Stats Checkboxes and Buttons
        chart_stats_widget = QtWidgets.QWidget()
        chart_stats_widget.setLayout(QtWidgets.QVBoxLayout())
        chart_stats_widget.layout().setDirection(QtWidgets.QBoxLayout.BottomToTop)
        chart_stats_widget.setFixedWidth(225)
        chart_stats_widget.setFixedHeight(900)
        chart_stats_widget.setAutoFillBackground(True)
        chart_stats_widget.layout().setSpacing(0)
        chart_stats_widget.layout().addStretch()

        self.chart_stats_checkboxes = dict()

        # Pixel samples stats
        self.show_pixel_samples_checkbox = QtWidgets.QCheckBox("Show/Hide Pixel Samples")
        self.show_pixel_samples_checkbox.setChecked(False)
        self.show_pixel_samples_checkbox.stateChanged.connect(self.show_pixel_samples)
        chart_stats_widget.layout().addWidget(self.show_pixel_samples_checkbox)
        chart_stats_widget.layout().addWidget(QtWidgets.QLabel(""))

        # Memory stats
        for stat in self.render_profile_chart.memory_stats:
            self.add_stat_checkbox(stat, chart_stats_widget, False)
        self.show_memory_checkbox = QtWidgets.QCheckBox("Show/Hide Memory Stats")
        self.show_memory_checkbox.setChecked(False)
        self.show_memory_checkbox.stateChanged.connect(self.show_memory)
        chart_stats_widget.layout().addWidget(self.show_memory_checkbox)
        chart_stats_widget.layout().addWidget(QtWidgets.QLabel("Memory Stats"))
        chart_stats_widget.layout().addWidget(QtWidgets.QLabel(""))

        # Render prep stats
        for stat in self.render_profile_chart.render_prep_stats:
            self.add_stat_checkbox(stat, chart_stats_widget, True)
        self.show_hide_render_prep_checkbox = QtWidgets.QCheckBox("Show/Hide Render Prep Stats")
        self.show_hide_render_prep_checkbox.setChecked(True)
        self.show_hide_render_prep_checkbox.stateChanged.connect(self.show_hide_render_prep_stats)
        chart_stats_widget.layout().addWidget(self.show_hide_render_prep_checkbox)
        chart_stats_widget.layout().addWidget(QtWidgets.QLabel("Render Prep Stats"))
        chart_stats_widget.layout().addWidget(QtWidgets.QLabel(""))

        # Scalar stats
        for stat in self.render_profile_chart.scalar_stats:
            self.add_stat_checkbox(stat, chart_stats_widget)
        self.show_hide_scalar_checkbox = QtWidgets.QCheckBox("Show/Hide Scalar Stats")
        self.show_hide_scalar_checkbox.setChecked(True)
        self.show_hide_scalar_checkbox.stateChanged.connect(self.show_hide_scalar_stats)
        chart_stats_widget.layout().addWidget(self.show_hide_scalar_checkbox)
        chart_stats_widget.layout().addWidget(QtWidgets.QLabel("Scalar Stats"))
        chart_stats_widget.layout().addWidget(QtWidgets.QLabel(""))

        # Vector stats
        for stat in self.render_profile_chart.vector_stats:
            self.add_stat_checkbox(stat, chart_stats_widget)
        self.show_hide_vector_checkbox = QtWidgets.QCheckBox("Show/Hide Vector Stats")
        self.show_hide_vector_checkbox.setChecked(True)
        self.show_hide_vector_checkbox.stateChanged.connect(self.show_hide_vector_stats)
        chart_stats_widget.layout().addWidget(self.show_hide_vector_checkbox)
        chart_stats_widget.layout().addWidget(QtWidgets.QLabel("Vector Stats"))
        chart_stats_widget.layout().addWidget(QtWidgets.QLabel(""))

        # XPU stats
        for stat in self.render_profile_chart.xpu_stats:
            self.add_stat_checkbox(stat, chart_stats_widget)
        chart_stats_widget.layout().addWidget(QtWidgets.QLabel("XPU Stats"))

        hide_all_button = QtWidgets.QPushButton("Hide All")
        hide_all_button.pressed.connect(self.hide_all_stats)
        chart_stats_widget.layout().addWidget(hide_all_button)

        show_all_button = QtWidgets.QPushButton("Show All")
        show_all_button.pressed.connect(self.show_all_stats)
        chart_stats_widget.layout().addWidget(show_all_button)

        chart_v_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)

        # Chart Tab
        chart_v_widget = QtWidgets.QWidget()
        chart_v_widget.setLayout(QtWidgets.QVBoxLayout())
        chart_v_splitter.addWidget(chart_v_widget)
        self.chart_image_log_tab_widget.addTab(chart_v_splitter, "Chart")

        chart_stats_h_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        chart_v_widget.layout().addWidget(chart_stats_h_splitter)
        chart_stats_h_splitter.setHandleWidth(10)

        chart_stats_scroll_area = QtWidgets.QScrollArea()
        chart_stats_scroll_area.setWidget(chart_stats_widget)
        chart_stats_h_splitter.addWidget(chart_stats_scroll_area)

        chart_stats_h_splitter.addWidget(self.render_profile_chart)
        chart_stats_h_splitter.setSizes([175, 800])

        # Test Types
        test_type_group_box = QtWidgets.QGroupBox()
        test_type_group_box.setLayout(QtWidgets.QVBoxLayout())
        test_type_group_box.setFixedHeight(group_box_height)
        test_type_group_box.setTitle("Test Types")
        tests_weeks_log_widget.layout().addWidget(test_type_group_box)

        self.scalar_checkbox = QtWidgets.QCheckBox("scalar")
        pal = QtGui.QPalette()
        pal.setColor(QtGui.QPalette.Base, self.render_profile_chart.scalar_color)
        pal.setColor(QtGui.QPalette.WindowText, self.render_profile_chart.scalar_color)
        self.scalar_checkbox.setPalette(pal)
        self.scalar_checkbox.setChecked(True)
        if self.log_file_mode:
            self.scalar_checkbox.stateChanged.connect(self.selection_changed_logs)
        else:
            self.scalar_checkbox.stateChanged.connect(self.selection_changed_weeks)
        test_type_group_box.layout().addWidget(self.scalar_checkbox)

        self.vector_checkbox = QtWidgets.QCheckBox("vector")
        pal = QtGui.QPalette()
        pal.setColor(QtGui.QPalette.Base, self.render_profile_chart.vector_color)
        pal.setColor(QtGui.QPalette.WindowText, self.render_profile_chart.vector_color)
        self.vector_checkbox.setPalette(pal)
        self.vector_checkbox.setChecked(True)
        if self.log_file_mode:
            self.vector_checkbox.stateChanged.connect(self.selection_changed_logs)
        else:
            self.vector_checkbox.stateChanged.connect(self.selection_changed_weeks)
        test_type_group_box.layout().addWidget(self.vector_checkbox)

        self.xpu_checkbox = QtWidgets.QCheckBox("xpu")
        pal = QtGui.QPalette()
        pal.setColor(QtGui.QPalette.Base, self.render_profile_chart.xpu_color)
        pal.setColor(QtGui.QPalette.WindowText, self.render_profile_chart.xpu_color)
        self.xpu_checkbox.setPalette(pal)
        self.xpu_checkbox.setChecked(True)
        if self.log_file_mode:
            self.xpu_checkbox.stateChanged.connect(self.selection_changed_logs)
        else:
            self.xpu_checkbox.stateChanged.connect(self.selection_changed_weeks)
        test_type_group_box.layout().addWidget(self.xpu_checkbox)

        # Image Tab
        self.image_widget = QtWidgets.QWidget()
        self.image_widget.setLayout(QtWidgets.QVBoxLayout())
        self.chart_image_log_tab_widget.addTab(self.image_widget, "Images")

        # Image Label
        self.image_label = QtWidgets.QLabel("")
        self.image_widget.layout().addWidget(self.image_label)

        # Show images button
        if self.log_file_mode:
            self.show_images_button = QtWidgets.QPushButton("Show images for selected logs with iv")
        else:
            self.show_images_button = QtWidgets.QPushButton("Show images for selected weeks with iv")
        self.show_images_button.setFixedWidth(250)
        self.show_images_button.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        self.show_images_button.pressed.connect(self.show_selected_images)
        self.image_widget.layout().addWidget(self.show_images_button)

        self.image_tab_widget = QtWidgets.QTabWidget()

        image_scale_widget = QtWidgets.QWidget()
        image_scale_widget.setLayout(QtWidgets.QHBoxLayout())
        image_scale_label = QtWidgets.QLabel("Image Scale")
        image_scale_widget.layout().addWidget(image_scale_label)

        self.image_size_spin_box = QtWidgets.QDoubleSpinBox()
        self.image_size_spin_box.setFixedWidth(50)
        self.image_size_spin_box.setSingleStep(0.01)
        self.image_size_spin_box.setDecimals(2)
        self.image_size_spin_box.setMinimum(0.1)
        self.image_size_spin_box.setMaximum(2.0)
        self.image_size_spin_box.setValue(1.0)
        self.image_size_spin_box.setEnabled(True)
        self.image_size_spin_box.valueChanged.connect(self.update_images)
        self.image_size_spin_box.setToolTip("Scale factor for displayed images")
        image_scale_widget.layout().addWidget(self.image_size_spin_box)
        image_scale_widget.layout().addStretch()

        self.image_widget.layout().addWidget(image_scale_widget)
        self.image_widget.layout().addWidget(self.image_tab_widget)
        #self.image_widget.layout().addStretch()

        # Logs Tab
        logs_widget = QtWidgets.QWidget()
        logs_widget.setLayout(QtWidgets.QVBoxLayout())
        logs_widget.layout().addWidget(QtWidgets.QLabel("Select a week to display log files"))
        self.chart_image_log_tab_widget.addTab(logs_widget, "Logs")

        # Font size
        log_font_size_widget = QtWidgets.QWidget()
        logs_widget.layout().addWidget(log_font_size_widget)
        log_font_size_widget.setLayout(QtWidgets.QHBoxLayout())
        log_font_size_widget.layout().addWidget(QtWidgets.QLabel("Font Size:"))
        self.log_font_size_spinner = QtWidgets.QSpinBox()
        self.log_font_size_spinner.setRange(1, 100)  # Set min and max font sizes
        self.log_font_size_spinner.setValue(12)  # Set default font size
        self.log_font_size_spinner.valueChanged.connect(self.change_logs_font_size)
        log_font_size_widget.layout().addWidget(self.log_font_size_spinner)
        log_font_size_widget.layout().addStretch()

        # Search UI
        search_widget = QtWidgets.QWidget()
        logs_widget.layout().addWidget(search_widget)
        search_widget.setLayout(QtWidgets.QHBoxLayout())
        search_widget.layout().addWidget(QtWidgets.QLabel("Search"))
        self.search_text = QtWidgets.QLineEdit()
        self.search_text.setFixedWidth(200)
        self.search_text.setClearButtonEnabled(True)
        self.search_text.returnPressed.connect(self.search_log_next)
        search_widget.layout().addWidget(self.search_text)
        self.search_next_button = QtWidgets.QPushButton("Find Next")
        self.search_next_button.clicked.connect(self.search_log_next)
        search_widget.layout().addWidget(self.search_next_button)
        self.search_previous_button = QtWidgets.QPushButton("Find Previous")
        self.search_previous_button.clicked.connect(self.search_log_previous)
        search_widget.layout().addWidget(self.search_previous_button)
        self.search_case_sensitive_checkbox = QtWidgets.QCheckBox("Case Sensitive")
        search_widget.layout().addWidget(self.search_case_sensitive_checkbox)
        search_widget.layout().addStretch()

        self.search_forward = True
        self.last_search = ""

        # Hold list of log browsers to determine which one to search
        self.log_browsers = []

        self.log_tab_widget = QtWidgets.QTabWidget()
        logs_widget.layout().addWidget(self.log_tab_widget)

        self.log_scalar_tab = None
        self.log_vector_tab = None
        self.log_xpu_tab = None

        # Bottom Scalar, Vector, and XPU Checkboxes and Resize
        chart_bottom_widget = QtWidgets.QWidget()
        chart_bottom_widget.setLayout(QtWidgets.QHBoxLayout())
        chart_v_splitter.addWidget(chart_bottom_widget)


        # Host Filter
        host_filter_group_box = QtWidgets.QGroupBox()
        host_filter_group_box.setLayout(QtWidgets.QVBoxLayout())
        host_filter_group_box.setFixedHeight(group_box_height)
        host_filter_group_box.setTitle("Host Filter")
        chart_bottom_widget.layout().addWidget(host_filter_group_box)

        self.host_filter_line_edit = QtWidgets.QLineEdit()
        self.host_filter_line_edit.setToolTip("List of space separated host prefixes "
                                              "to filter by (i.e. \"ws p920 tin\"")
        self.host_filter_line_edit.editingFinished.connect(self.update_chart)
        host_filter_group_box.layout().addWidget(self.host_filter_line_edit)

        self.show_hosts_in_chart_checkbox = QtWidgets.QCheckBox("Show host names in chart")
        self.show_hosts_in_chart_checkbox.setToolTip("Show the names of the hosts instead of dates/types in the chart")
        self.show_hosts_in_chart_checkbox.setChecked(False)
        self.show_hosts_in_chart_checkbox.stateChanged.connect(self.update_chart)
        host_filter_group_box.layout().addWidget(self.show_hosts_in_chart_checkbox)

        # Options
        options_group_box = QtWidgets.QGroupBox()
        options_group_box.setLayout(QtWidgets.QVBoxLayout())
        options_group_box.layout().setSpacing(0)
        options_group_box.setTitle("Options")
        chart_bottom_widget.layout().addWidget(options_group_box)
        options_group_box.setFixedHeight(group_box_height)

        self.divide_by_ps_checkbox = QtWidgets.QCheckBox("Divide by Pixel Samples")
        self.divide_by_ps_checkbox.setChecked(False)
        self.divide_by_ps_checkbox.stateChanged.connect(lambda: self.update_chart(resize=True))
        options_group_box.layout().addWidget(self.divide_by_ps_checkbox)

        self.show_trend_lines_checkbox = QtWidgets.QCheckBox("Show Trend Lines")
        self.show_trend_lines_checkbox.setChecked(True)
        self.show_trend_lines_checkbox.stateChanged.connect(lambda: self.update_chart(resize=True))
        options_group_box.layout().addWidget(self.show_trend_lines_checkbox)

        self.show_fallback_checkbox = QtWidgets.QCheckBox("Show Fallback")
        pal = QtGui.QPalette()
        pal.setColor(QtGui.QPalette.Base, self.render_profile_chart.fallback_color)
        self.show_fallback_checkbox.setPalette(pal)
        self.show_fallback_checkbox.setChecked(True)
        self.show_fallback_checkbox.stateChanged.connect(lambda: self.update_chart(resize=True))
        options_group_box.layout().addWidget(self.show_fallback_checkbox)

        self.show_crash_checkbox = QtWidgets.QCheckBox("Show Crash")
        pal = QtGui.QPalette()
        pal.setColor(QtGui.QPalette.Base, self.render_profile_chart.crash_color)
        self.show_crash_checkbox.setPalette(pal)
        self.show_crash_checkbox.setChecked(True)
        self.show_crash_checkbox.stateChanged.connect(lambda: self.update_chart(resize=True))
        options_group_box.layout().addWidget(self.show_crash_checkbox)

        options_group_box.layout().addStretch()

        # Bottom Performance Thresholds
        performance_thresholds_group_box = QtWidgets.QGroupBox()
        performance_thresholds_group_box.setLayout(QtWidgets.QHBoxLayout())
        performance_thresholds_group_box.layout().setDirection(QtWidgets.QBoxLayout.RightToLeft)
        performance_thresholds_group_box.setTitle("Performance Thresholds")
        performance_thresholds_group_box.setFixedHeight(group_box_height)
        chart_bottom_widget.layout().addWidget(performance_thresholds_group_box)

        self.improvement_warning_checkbox = QtWidgets.QCheckBox("Show Improvements")
        pal = QtGui.QPalette()
        pal.setColor(QtGui.QPalette.Base, self.render_profile_chart.improvements_color)
        self.improvement_warning_checkbox.setPalette(pal)
        self.improvement_warning_checkbox.setChecked(False)
        self.improvement_warning_checkbox.stateChanged.connect(self.checkbox_changed_improvements)
        self.improvement_warning_checkbox.setToolTip("Highlight stats that have improved more than this "
                                                     " percentage from the previous week in green")
        performance_thresholds_group_box.layout().addWidget(self.improvement_warning_checkbox)

        self.improvement_warning_spin_box = QtWidgets.QSpinBox()
        self.improvement_warning_spin_box.setMinimum(0)
        self.improvement_warning_spin_box.setMaximum(100)
        self.improvement_warning_spin_box.setValue(10)
        self.improvement_warning_spin_box.setEnabled(False)
        self.improvement_warning_spin_box.valueChanged.connect(self.update_chart)
        self.improvement_warning_spin_box.setToolTip("Highlight stats that have improved more than this "
                                                     " percentage from the previous week in green")
        performance_thresholds_group_box.layout().addWidget(self.improvement_warning_spin_box)

        self.regression_warning_checkbox = QtWidgets.QCheckBox("Show Regressions")
        pal = QtGui.QPalette()
        pal.setColor(QtGui.QPalette.Base, self.render_profile_chart.regression_color)
        self.regression_warning_checkbox.setPalette(pal)
        self.regression_warning_checkbox.setChecked(False)
        self.regression_warning_checkbox.stateChanged.connect(self.checkbox_changed_regressions)
        self.regression_warning_checkbox.setToolTip("Highlight stats that have regressed more than this "
                                                    " percentage from the previous week in red")
        performance_thresholds_group_box.layout().addWidget(self.regression_warning_checkbox)
        self.regression_warning_spin_box = QtWidgets.QSpinBox()
        self.regression_warning_spin_box.setMinimum(0)
        self.regression_warning_spin_box.setMaximum(100)
        self.regression_warning_spin_box.setValue(10)
        self.regression_warning_spin_box.setEnabled(False)
        self.regression_warning_spin_box.valueChanged.connect(self.update_chart)
        self.regression_warning_spin_box.setToolTip("Highlight stats that have regressed more than this "
                                                    " percentage from the previous week in red")
        performance_thresholds_group_box.layout().addWidget(self.regression_warning_spin_box)

        # Font Size
        self.font_size = 11

        # Bottom View Controls
        view_group_box = QtWidgets.QGroupBox()
        view_group_box.setFixedHeight(group_box_height)
        view_group_box.setLayout(QtWidgets.QHBoxLayout())

        view_group_box.setTitle("View")
        view_group_box.setToolTip("Use the buttons or press 'wasd' to scroll,"
                                  "'q' to zoom out, 'e' to zoom in, and 'r' to home")
        chart_bottom_widget.layout().addWidget(view_group_box)

        resize_button = QtWidgets.QPushButton("Refit Chart")
        resize_button.setToolTip("Reset the view to fit the current chart - can also press 'Home' or 'r'")
        resize_button.setFixedWidth(100)
        resize_button.pressed.connect(lambda: self.update_chart(resize=True))
        view_group_box.layout().addWidget(resize_button)

        chart_bottom_widget.layout().addStretch()

        main_h_splitter.setSizes([250, 1350])

        self.show()

        # Set initial dark theme
        app = QtWidgets.QApplication.instance()
        palette = app.palette()
        palette.setColor(QtGui.QPalette.Window, QtGui.QColor(50, 50, 50))
        palette.setColor(QtGui.QPalette.Button, QtGui.QColor(70, 70, 70))
        palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(255, 255, 255))
        palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor(255, 255, 255))
        palette.setColor(QtGui.QPalette.Text, QtGui.QColor(255, 255, 255))
        palette.setColor(QtGui.QPalette.Base, QtGui.QColor(70, 70, 70))
        app.setPalette(palette)
        self.setStyleSheet(f'font-size: {self.font_size}px')

        if self.log_file_mode:
            self.logs_list.setCurrentRow(0)
        else:
            # Select first row and show chars
            self.tests_list.setCurrentRow(0)
            self.selection_changed_tests()
            self.weeks_list.selectAll()

    def log_list_context_menu(self, position):
        pop_menu = QtWidgets.QMenu()

        if self.logs_list.itemAt(position):
            set_test_name_action = QtWidgets.QAction("Set test name")
            set_test_name_action.triggered.connect(self.set_custom_log_name)
            pop_menu.addAction(set_test_name_action)
            pop_menu.exec_(self.logs_list.mapToGlobal(position))

    def set_custom_log_name(self):
        selected_item = self.logs_list.selectedItems()[0]
        user_role_dict = selected_item.data(QtCore.Qt.UserRole)
        test_name = user_role_dict["name"]

        new_test_name, ok = QtWidgets.QInputDialog.getText(self,
                                                           "Set test name",
                                                           "Enter new test name",
                                                           QtWidgets.QLineEdit.Normal,
                                                           test_name)

        if ok:
            selected_item.setText(new_test_name)
            user_role_dict["name"] = new_test_name
            selected_item.setData(QtCore.Qt.UserRole, user_role_dict)
            self.selection_changed_logs()

    # noinspection PyTypeChecker
    def set_profile_dir(self):
        self.profile_directory = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select profile report directory",
            self.profile_directory,
            QtWidgets.QFileDialog.ShowDirsOnly | QtWidgets.QFileDialog.DontResolveSymlinks
        )
        self.setWindowTitle(f"Render Profile Viewer {__version__} -- (Profile directory: {self.profile_directory})")

        self.populate_test_list()
        self.tests_list.setCurrentRow(0)
        self.selection_changed_tests()
        self.weeks_list.selectAll()
        self.selection_changed_weeks()

    # noinspection PyTypeChecker
    def set_cache_dir(self):
        self.cache_directory = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select cache directory",
            self.cache_directory,
            QtWidgets.QFileDialog.ShowDirsOnly | QtWidgets.QFileDialog.DontResolveSymlinks
        )

    def clear_cache_dir(self):
        shutil.rmtree(self.cache_directory,
                      ignore_errors=False)
        os.makedirs(self.cache_directory)

    def set_use_cache(self):
        self.use_cache = not self.use_cache

    def set_dark_theme(self):
        app = QtWidgets.QApplication.instance()
        palette = app.palette()
        palette.setColor(QtGui.QPalette.Window, QtGui.QColor(50, 50, 50))
        palette.setColor(QtGui.QPalette.Button, QtGui.QColor(70, 70, 70))
        palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(255, 255, 255))
        palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor(255, 255, 255))
        palette.setColor(QtGui.QPalette.Text, QtGui.QColor(255, 255, 255))
        palette.setColor(QtGui.QPalette.Base, QtGui.QColor(70, 70, 70))
        app.setPalette(palette)
        self.setStyleSheet(f'font-size: {self.font_size}px')
        self.use_dark_theme = True
        self.update_chart()

    def set_light_theme(self):
        app = QtWidgets.QApplication.instance()
        palette = app.palette()
        palette.setColor(QtGui.QPalette.Window, QtGui.QColor(239, 239, 239))
        palette.setColor(QtGui.QPalette.Button, QtGui.QColor(239, 239, 239))
        palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(0, 0, 0))
        palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor(0, 0, 0))
        palette.setColor(QtGui.QPalette.Text, QtGui.QColor(0, 0, 0))
        palette.setColor(QtGui.QPalette.Base, QtGui.QColor(255, 255, 255))
        app.setPalette(palette)
        self.setStyleSheet(f'font-size: {self.font_size}px')
        self.use_dark_theme = False
        self.update_chart()

    def checkbox_changed_improvements(self):
        if self.improvement_warning_checkbox.isChecked():
            self.improvement_warning_spin_box.setEnabled(True)
        else:
            self.improvement_warning_spin_box.setEnabled(False)
        self.update_chart()

    def checkbox_changed_regressions(self):
        if self.regression_warning_checkbox.isChecked():
            self.regression_warning_spin_box.setEnabled(True)
        else:
            self.regression_warning_spin_box.setEnabled(False)
        self.update_chart()

    def checkbox_changed_full_paths(self):
        for row in range(self.logs_list.count()):
            item = self.logs_list.item(row)
            user_role_dict = item.data(QtCore.Qt.UserRole)
            if self.show_full_paths_checkbox.isChecked():
                item.setText(user_role_dict["path"])
            else:
                item.setText(user_role_dict["name"])

    def font_size_increase(self):
        if self.font_size <= 50:
            self.font_size += 2
            self.setStyleSheet(f'font-size: {self.font_size}px')
            self.update_chart(resize=False)

    def font_size_decrease(self):
        if self.font_size >= 5:
            self.font_size -= 2
            self.setStyleSheet(f'font-size: {self.font_size}px')
            self.update_chart(resize=False)

    def set_chart_label_angle(self):
        angle, ok = QtWidgets.QInputDialog.getDouble(self,
                                                     "Set chart labels angle",
                                                     "Enter new angle",
                                                     self.chart_label_angle,
                                                     -360.0, 360.0)

        if ok:
            self.chart_label_angle = angle
            self.update_chart()

    def show_all_stats(self):
        for stat in self.chart_stats_checkboxes.keys():
            self.chart_stats_checkboxes[stat].setChecked(True)
        self.show_hide_vector_checkbox.setChecked(True)
        self.show_hide_scalar_checkbox.setChecked(True)
        self.show_hide_render_prep_checkbox.setChecked(True)
        self.update_chart(resize=True)

    def hide_all_stats(self):
        for stat in self.chart_stats_checkboxes.keys():
            self.chart_stats_checkboxes[stat].setChecked(False)

        self.show_hide_vector_checkbox.setChecked(False)
        self.show_hide_scalar_checkbox.setChecked(False)
        self.show_hide_render_prep_checkbox.setChecked(False)
        self.update_chart()

    def show_hide_scalar_stats(self):
        for stat in self.render_profile_chart.scalar_stats:
            if self.show_hide_scalar_checkbox.isChecked():
                self.chart_stats_checkboxes[stat].setChecked(True)
            else:
                self.chart_stats_checkboxes[stat].setChecked(False)
        self.update_chart(resize=False)

    def show_hide_render_prep_stats(self):
        for stat in self.render_profile_chart.render_prep_stats:
            if self.show_hide_render_prep_checkbox.isChecked():
                self.chart_stats_checkboxes[stat].setChecked(True)
            else:
                self.chart_stats_checkboxes[stat].setChecked(False)
        self.update_chart(resize=False)

    def show_hide_vector_stats(self):
        for stat in self.render_profile_chart.vector_stats:
            if self.show_hide_vector_checkbox.isChecked():
                self.chart_stats_checkboxes[stat].setChecked(True)
            else:
                self.chart_stats_checkboxes[stat].setChecked(False)
        self.update_chart(resize=False)

    def show_pixel_samples(self):
        stats = self.render_profile_chart.render_prep_stats +\
                self.render_profile_chart.scalar_stats +\
                self.render_profile_chart.vector_stats +\
                self.render_profile_chart.xpu_stats
        if self.show_pixel_samples_checkbox.isChecked():
            self.show_memory_checkbox.setChecked(False)
            self.show_hide_render_prep_checkbox.setEnabled(False)
            self.show_hide_scalar_checkbox.setEnabled(False)
            self.show_hide_vector_checkbox.setEnabled(False)
            for stat in stats:
                self.chart_stats_checkboxes[stat].setEnabled(False)
        else:
            self.show_hide_render_prep_checkbox.setEnabled(True)
            self.show_hide_scalar_checkbox.setEnabled(True)
            self.show_hide_vector_checkbox.setEnabled(True)
            for stat in stats:
                self.chart_stats_checkboxes[stat].setEnabled(True)
        self.update_chart(resize=True)

    def show_memory(self):
        stats = self.render_profile_chart.render_prep_stats + \
                self.render_profile_chart.scalar_stats + \
                self.render_profile_chart.vector_stats + \
                self.render_profile_chart.xpu_stats
        if self.show_memory_checkbox.isChecked():
            self.show_pixel_samples_checkbox.setChecked(False)
            self.show_hide_render_prep_checkbox.setEnabled(False)
            self.show_hide_scalar_checkbox.setEnabled(False)
            self.show_hide_vector_checkbox.setEnabled(False)
            for stat in stats:
                self.chart_stats_checkboxes[stat].setEnabled(False)
            for stat in self.render_profile_chart.memory_stats:
                self.chart_stats_checkboxes[stat].setChecked(True)
                self.chart_stats_checkboxes[stat].setEnabled(True)
        else:
            self.show_hide_render_prep_checkbox.setEnabled(True)
            self.show_hide_scalar_checkbox.setEnabled(True)
            self.show_hide_vector_checkbox.setEnabled(True)
            for stat in stats:
                self.chart_stats_checkboxes[stat].setEnabled(True)
            for stat in self.render_profile_chart.memory_stats:
                self.chart_stats_checkboxes[stat].setChecked(False)
                self.chart_stats_checkboxes[stat].setEnabled(False)
        self.update_chart(resize=True)

    def add_stat_checkbox(self, stat, stats_widget, default_state=True):
        check_box = QtWidgets.QCheckBox(stat)
        check_box.setChecked(default_state)
        check_box.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Minimum)
        check_box.setFixedHeight(18)
        check_box.clicked.connect(lambda: self.update_chart(resize=False))

        check_box_color = self.render_profile_chart.stat_colors[stat]
        pal = QtGui.QPalette()
        pal.setColor(QtGui.QPalette.Window, check_box_color)
        pal.setColor(QtGui.QPalette.Base, check_box_color)
        check_box.setPalette(pal)
        check_box.update()

        stats_widget.layout().addWidget(check_box)
        self.chart_stats_checkboxes[stat] = check_box

    def get_test_dir(self, test_name):
        return os.path.join(self.profile_directory, test_name)

    def selection_changed_tests(self):
        prev_selected_weeks = [i.text() for i in self.weeks_list.selectedItems()]

        self.weeks_list.clear()
        self.stats.clear()
        if len(self.tests_list.selectedItems()) == 0:
            return

        test_name = self.tests_list.selectedItems()[0].text()

        weeks = set()
        test_dir = self.get_test_dir(test_name)
        with os.scandir(test_dir) as files:
            for f in files:
                if not f.is_dir():
                    week = f.name.split('_')[0]
                    weeks.add(week)

        self.process_weeks = False
        for w in sorted(weeks):
            week_item = QtWidgets.QListWidgetItem(w)
            self.weeks_list.addItem(week_item)
            if w in prev_selected_weeks:
                week_item.setSelected(True)
        self.process_weeks = True
        self.selection_changed_weeks()

    def get_log_path(self, test_name, week, exec_mode):
        test_dir = self.get_test_dir(test_name)
        with os.scandir(test_dir) as files:
            for f in files:
                if not f.is_dir():
                    if fnmatch.fnmatch(f.name, f"{week}_*_{exec_mode}.txt"):
                        log_path = os.path.join(test_dir, f.name)
                        return log_path

        return None

    def search_log_next(self):
        self.search_forward = True
        self.search_log()

    def search_log_previous(self):
        self.search_forward = False
        self.search_log()

    def search_log(self):
        if len(self.log_browsers) == 0:
            return
        browser_widget = self.log_browsers[self.log_tab_widget.currentIndex()]

        search_text = self.search_text.text()
        if not search_text:
            return

        if not self.last_search or (self.last_search and search_text != self.last_search):
            # Reset cursor to beginning
            cursor = browser_widget.textCursor()
            cursor.setPosition(0)
            browser_widget.setTextCursor(cursor)
            self.last_search = search_text

        # Determine search flags
        flags = browser_widget.document().FindFlags()
        if not self.search_forward:
            flags |= browser_widget.document().FindBackward
        if self.search_case_sensitive_checkbox.isChecked():
            flags |= browser_widget.document().FindCaseSensitively

        found = browser_widget.find(self.last_search, flags)

        if found:
            # Text is found, it's now selected
            pass
        else:
            # If not found, wrap around
            cursor = browser_widget.textCursor()
            if self.search_forward:
                cursor.movePosition(QtGui.QTextCursor.Start)
            else:
                cursor.movePosition(QtGui.QTextCursor.End)
            browser_widget.setTextCursor(cursor)
            found = browser_widget.find(self.last_search, flags)
            if not found:
                QtWidgets.QMessageBox.information(self, "Find Next", f"No more occurances of '{self.last_search}'")

    def process_logs(self, test_name, test_type):
        # selectedItems needs to handle profile runs that run into the next day better.
        for i, item in enumerate(sorted(self.weeks_list.selectedItems())):
            week = item.text()
            if week not in self.stats:
                self.stats[week] = dict()
            log_path = self.get_log_path(test_name, week, test_type)
            if not log_path:
                next_day = str(datetime.datetime.strptime(week, "%Y-%m-%d").date() +
                               datetime.timedelta(days=1))
                log_path = self.get_log_path(test_name, next_day, test_type)
                if not log_path:
                    prev_day = str(datetime.datetime.strptime(week, "%Y-%m-%d").date() -
                                   datetime.timedelta(days=1))
                    log_path = self.get_log_path(test_name, prev_day, test_type)
                    if not log_path:
                        self.stats[week][test_type] = "missing"
            if log_path:
                if test_type not in self.stats[week]:
                    self.stats[week][test_type] = self.get_stats(test_name, week, log_path, test_type)
                if i == 0:
                    self.create_log_widget(log_path, test_type)

    def apply_ansi_escape_codes(self, log_browser, text):
        cursor = log_browser.textCursor()
        cursor.movePosition(QtGui.QTextCursor.Start)

        # ANSI color codes
        ansi_color_codes = {
            '30': QColor(0, 0, 0),  # Black
            '31': QColor(255, 0, 0),  # Red
            '32': QColor(0, 255, 0),  # Green
            '33': QColor(255, 255, 0),  # Yellow
            '34': QColor(0, 0, 255),  # Blue
            '35': QColor(255, 0, 255),  # Magenta
            '36': QColor(0, 255, 255),  # Cyan
            '37': QColor(255, 255, 255),  # White
            '90': QColor(128, 128, 128),  # Bright Black (Gray)
            '91': QColor(255, 0, 0),  # Bright Red
            '92': QColor(0, 255, 0),  # Bright Green
            '93': QColor(255, 255, 0),  # Bright Yellow
            '94': QColor(0, 0, 255),  # Bright Blue
            '95': QColor(255, 0, 255),  # Bright Magenta
            '96': QColor(0, 255, 255),  # Bright Cyan
            '97': QColor(255, 255, 255),  # Bright White
        }

        # Regular expression to match ANSI escape codes
        ansi_escape = re.compile(r'\x1b\[((?:\d+;)*\d+)m')

        # Split the text by ANSI escape codes
        fragments = ansi_escape.split(text)

        for i, fragment in enumerate(fragments):
            if i % 2 == 0:
                # This is a text fragment
                cursor.insertText(fragment)
            else:
                # This is an ANSI code fragment
                codes = fragment.split(';')
                format = QTextCharFormat()

                for code in codes:
                    if code in ansi_color_codes:
                        format.setForeground(ansi_color_codes[code])
                    elif code == '1':
                        format.setFontWeight(QtGui.QFont.Bold)
                    elif code == '3':
                        format.setFontItalic(True)
                    elif code == '4':
                        format.setFontUnderline(True)
                    # Add more code handlers as needed

                cursor.setCharFormat(format)

        log_browser.setTextCursor(cursor)
        log_browser.moveCursor(QtGui.QTextCursor.Start)

    def create_log_widget(self, log_path, test_type):
        log_widget = QtWidgets.QWidget()
        log_widget.setLayout(QtWidgets.QVBoxLayout())
        log_browser = QtWidgets.QTextBrowser()
        # Set the stylesheet for the QTextBrowser
        log_browser.setStyleSheet("""
            QTextBrowser {
                background-color: black;
                color: white;
            }
            QTextBrowser::selection {
                background-color: yellow;
                color: black;
            }
        """)

        # Set initial monospace font
        font = QtGui.QFont("Courier")
        font.setStyleHint(QtGui.QFont.Monospace)
        font.setFixedPitch(True)
        font.setPointSize(self.log_font_size_spinner.value())
        log_browser.setFont(font)

        self.log_browsers.append(log_browser)

        self.set_log_text(log_browser, log_path)
        log_widget.layout().addWidget(log_browser)

        if test_type == 'scalar':
            if self.log_scalar_tab == None:
                self.log_scalar_tab = QtWidgets.QTabWidget()
                self.log_tab_widget.addTab(self.log_scalar_tab, "scalar")
            self.log_scalar_tab.addTab(log_widget, os.path.basename(log_path))
        elif test_type == 'vector':
            if self.log_vector_tab == None:
                self.log_vector_tab = QtWidgets.QTabWidget()
                self.log_tab_widget.addTab(self.log_vector_tab, "vector")
            self.log_vector_tab.addTab(log_widget, os.path.basename(log_path))
        elif test_type == 'xpu':
            if self.log_xpu_tab == None:
                self.log_xpu_tab = QtWidgets.QTabWidget()
                self.log_tab_widget.addTab(self.log_xpu_tab, "xpu")
            self.log_xpu_tab.addTab(log_widget, os.path.basename(log_path))


    def change_log_font_size(self, log_browser, size):
        # Create a new font with the desired size
        new_font = log_browser.font()
        new_font.setPointSize(size)
        # Set the new font as the default for the document
        log_browser.document().setDefaultFont(new_font)
        # Update the viewport to reflect the changes
        log_browser.viewport().update()

    def change_logs_font_size(self, size):
        for log_browser in self.log_browsers:
            self.change_log_font_size(log_browser, size)

    def selection_changed_weeks(self):
        if not self.process_weeks:
            return
        self.stats.clear()
        if len(self.tests_list.selectedItems()) == 0:
            return

        # Reset log browser list
        self.log_browsers = []
        self.log_scalar_tab = None
        self.log_vector_tab = None
        self.log_xpu_tab = None
        self.log_tab_widget.clear()

        test_name = self.tests_list.selectedItems()[0].text()
        if self.scalar_checkbox.isChecked():
            self.process_logs(test_name, 'scalar')
        if self.vector_checkbox.isChecked():
            self.process_logs(test_name, 'vector')
        if self.xpu_checkbox.isChecked():
            self.process_logs(test_name, 'xpu')

        # Set initial font size
        self.change_logs_font_size(self.log_font_size_spinner.value())

        self.update_chart(resize=True)

        try:
            self.update_images()
        except (RuntimeError, KeyError) as e:
            print(f"Caught an exception: {e}")


    def get_unique_test_name(self, test_name, log_file):
        dir_name = os.path.dirname(log_file)
        dirs = dir_name.split('/')
        i = 1
        while test_name in self.stats:
            test_name = f"{dirs[-i]}_{test_name}"
            i += 1
        return test_name

    def selection_changed_logs(self):
        self.stats.clear()
        if len(self.logs_list.selectedItems()) == 0:
            return

        self.log_tab_widget.clear()
        current_tab_index = self.chart_image_log_tab_widget.currentIndex()
        for i, item in enumerate(self.logs_list.selectedItems()):
            user_role_dict = item.data(QtCore.Qt.UserRole)
            log_file = user_role_dict["path"]
            test_name = user_role_dict["name"]
            test_display_name = user_role_dict["name"]
            if test_name in self.stats:
                test_name = self.get_unique_test_name(test_name, log_file)
            week = 'none'

            log_type = 'scalar'
            if fnmatch.fnmatch(test_name, f"*_vector.txt"):
                log_type = 'vector'
            if fnmatch.fnmatch(test_name, f"*_xpu.txt"):
                log_type = 'xpu'

            stats = self.get_stats(test_name,
                                   week,
                                   log_file,
                                   log_type)

            if stats:
                self.stats[test_name] = dict()
                self.stats[test_name][log_type] = stats
                self.stats[test_name][log_type]['display_name'] = test_display_name

            if i == 0 and current_tab_index == 2:
                log_widget = QtWidgets.QTextBrowser()
                self.set_log_text(log_widget, log_file)
                self.log_tab_widget.addTab(log_widget, test_name)

        self.update_chart(resize=True)


    def update_images(self):
        self.image_tab_widget.clear()
        scalar_tab = None
        vector_tab = None
        xpu_tab = None
        for week in self.stats:
            for test_type in self.stats[week]:
                QtCore.QCoreApplication.processEvents()
                if (test_type == 'scalar' and self.scalar_checkbox.isChecked()) or \
                   (test_type == 'vector' and self.vector_checkbox.isChecked()) or \
                   (test_type == 'xpu' and self.xpu_checkbox.isChecked()):

                    if 'output_image' not in self.stats[week][test_type]:
                        continue

                    output_image = self.stats[week][test_type]['output_image']

                    q_image = None
                    image_width = 0
                    image_height = 0
                    if output_image in self.images_cache:
                        (q_image, image_width, image_height) = self.images_cache[output_image]
                    else:
                        if os.path.exists(output_image):
                            if not output_image in self.images_cache:
                                (q_image, image_width, image_height) = load_exr_as_qimage(output_image)
                                self.images_cache[output_image] = (q_image, image_width, image_height)
                        else:
                            print(f"Error: Image file not found: {output_image}")
                            continue

                    image_widget = QtWidgets.QWidget()
                    image_widget.setLayout(QtWidgets.QVBoxLayout())
                    image_scroll_area = QtWidgets.QScrollArea()
                    image_scroll_area.setWidgetResizable(True)
                    image_widget.layout().addWidget(image_scroll_area)

                    image_label = QtWidgets.QLabel("")
                    image_label.setAlignment(QtCore.Qt.AlignCenter)
                    image_label.setProperty('image_path', output_image)
                    image_label.setScaledContents(False)
                    size_factor = self.image_size_spin_box.value()
                    w = int(size_factor * image_width)
                    h = int(size_factor * image_height)

                    pixmap = QtGui.QPixmap(q_image)
                    image_label.setPixmap(pixmap.scaled(w, h,
                                                        QtCore.Qt.KeepAspectRatio,
                                                        QtCore.Qt.SmoothTransformation))
                    image_scroll_area.setWidget(image_label)

                    if self.log_file_mode:
                        tab_name = self.stats[week][test_type]['display_name']
                    else:
                        tab_name = f"{week}_{test_type}"

                    if test_type == 'scalar':
                        if scalar_tab == None:
                            scalar_tab = QtWidgets.QTabWidget()
                            self.image_tab_widget.addTab(scalar_tab, "scalar")
                        scalar_tab.addTab(image_widget, tab_name)
                    elif test_type == 'vector':
                        if vector_tab == None:
                            vector_tab = QtWidgets.QTabWidget()
                            self.image_tab_widget.addTab(vector_tab, "vector")
                        vector_tab.addTab(image_widget, tab_name)
                    elif test_type == 'xpu':
                        if xpu_tab == None:
                            xpu_tab = QtWidgets.QTabWidget()
                            self.image_tab_widget.addTab(xpu_tab, "xpu")
                        xpu_tab.addTab(image_widget, tab_name)

    def show_selected_images(self):
        cmd = ['iv']
        for week in self.stats:
            for test_type in self.stats[week]:

                if (test_type == 'scalar' and self.scalar_checkbox.isChecked()) or \
                   (test_type == 'vector' and self.vector_checkbox.isChecked()) or \
                   (test_type == 'xpu' and self.xpu_checkbox.isChecked()):

                    if 'output_image' in self.stats[week][test_type]:
                        output_image = self.stats[week][test_type]['output_image']
                        if os.path.exists(output_image):
                            cmd.append(output_image)
                        else:
                            print(f"Error: Image file not found: {output_image}")
                            return
        subprocess.Popen(cmd)

    def update_chart(self, resize=False):
        stats_visibility_list = list()
        for stat in self.chart_stats_checkboxes.keys():
            if self.show_memory_checkbox.isChecked():
                if stat in self.render_profile_chart.memory_stats and \
                        self.chart_stats_checkboxes[stat].isChecked():
                    stats_visibility_list.append(stat)
            elif self.chart_stats_checkboxes[stat].isChecked():
                stats_visibility_list.append(stat)

        host_visibility_list = self.host_filter_line_edit.text().split()

        my_stats = copy.deepcopy(self.stats)

        # Divide by pixel samples
        if self.divide_by_ps_checkbox.isChecked():
            for week in my_stats:
                for typ in my_stats[week]:
                    if 'pixel_samples' in my_stats[week][typ]:
                        pixel_samples = my_stats[week][typ]['pixel_samples'] * 1000000
                        for stat_name in my_stats[week][typ]:
                            if not stat_name == "pixel_samples" and isinstance(my_stats[week][typ][stat_name], float):
                                my_stats[week][typ][stat_name] /= pixel_samples
                    else:
                        print(f"Error: No pixel_samples data for {week}")

        # Calculate total time for visible stats
        for week in my_stats:
            for test_type in my_stats[week]:
                if not my_stats[week][test_type] or my_stats[week][test_type] == "missing":
                    continue
                visible_time = 0.0
                if self.show_pixel_samples_checkbox.isChecked():
                    visible_time = my_stats[week][test_type]['pixel_samples']
                else:
                    for stat in my_stats[week][test_type]:
                        if stat in stats_visibility_list:
                            visible_time += my_stats[week][test_type][stat]
                my_stats[week][test_type]['visible_time'] = visible_time

        type_visibility_list = list()
        if self.scalar_checkbox.isChecked():
            type_visibility_list.append('scalar')
        if self.vector_checkbox.isChecked():
            type_visibility_list.append('vector')
        if self.xpu_checkbox.isChecked():
            type_visibility_list.append('xpu')

        if self.log_file_mode:
            if len(self.logs_list.selectedItems()) > 1:
                test_name = ""
            else:
                test_name = self.logs_list.selectedItems()[0].text()
        else:
            test_name = self.tests_list.selectedItems()[0].text()

        self.render_profile_chart.update_chart(test_name,
                                               my_stats,
                                               self.show_pixel_samples_checkbox.isChecked(),
                                               self.show_memory_checkbox.isChecked(),
                                               self.show_hosts_in_chart_checkbox.isChecked(),
                                               type_visibility_list,
                                               host_visibility_list,
                                               stats_visibility_list,
                                               resize,
                                               self.font_size,
                                               self.regression_warning_checkbox.isChecked(),
                                               self.regression_warning_spin_box.value(),
                                               self.improvement_warning_checkbox.isChecked(),
                                               self.improvement_warning_spin_box.value(),
                                               self.use_dark_theme,
                                               self.show_trend_lines_checkbox.isChecked(),
                                               self.divide_by_ps_checkbox.isChecked(),
                                               self.show_fallback_checkbox.isChecked(),
                                               self.show_crash_checkbox.isChecked(),
                                               self.chart_label_angle)

    def set_log_text(self, log_widget, log_file):
        if not log_file:
            log_widget.setText(f"Log: does not exist")
            return

        if os.path.exists(log_file):
            with open(log_file, 'r') as log_file:
                log_file_text = log_file.read()
            #log_widget.setText(log_file_text)
            log_widget.clear()
            self.apply_ansi_escape_codes(log_widget, log_file_text)
        else:
            log_widget.setText(f"Log: {log_file} does not exist")

    def populate_test_list(self):
        self.tests_list.clear()
        with os.scandir(self.profile_directory) as test_dirs:
            for t in test_dirs:
                if t.is_dir():
                    test_item = QtWidgets.QListWidgetItem(t.name)
                    self.tests_list.addItem(test_item)

    def add_log_file_to_list(self, log_file):
        extension = os.path.splitext(log_file)[1]
        if extension != '.txt' and extension != '.log':
            return
        user_role_dict = dict()
        path = os.path.abspath(log_file)
        name = os.path.basename(path)
        user_role_dict["name"] = name
        user_role_dict["path"] = path
        display_text = path
        if self.show_full_paths_checkbox.isChecked():
            display_text = path
        item = QtWidgets.QListWidgetItem(display_text)
        item.setData(QtCore.Qt.UserRole, user_role_dict)
        item.setToolTip(path)
        self.logs_list.addItem(item)

    def add_log_files_to_list(self, log_file):
        if os.path.isdir(log_file):
            with os.scandir(log_file) as files:
                for f in files:
                    self.add_log_files_to_list(f.path)
        else:
            self.add_log_file_to_list(log_file)

    def populate_logs_list(self):
        self.logs_list.clear()
        for l in self.log_files:
            self.add_log_files_to_list(l)
        self.logs_list.sortItems()

    def parse_log_file(self, log_file):
        fallback_re = re.compile(r"Executing a (.*) render since execution mode was set to ([^.]*).")
        in_breakdown = False
        in_render_prep = False
        in_render_prep_memory = False
        found_wrote_line = False
        found_breakdown = False
        stats = dict()
        stats['fallback'] = False
        stats['crash'] = False
        with open(log_file) as f:
            for line in f:
                match = fallback_re.match(line)
                if match:
                    if len(match.groups()) == 2:
                        if (match.group(1) == 'scalar' and match.group(2) == 'xpu') or \
                                (match.group(1) == 'vector' and match.group(2) == 'xpu') or \
                                (match.group(1) == 'scalar' and match.group(2) == 'vector') or \
                                (match.group(1) == 'vector' and match.group(2) == 'auto') or \
                                (match.group(1) == 'scalar' and match.group(2) == 'auto'):
                            stats['fallback'] = True
                            stats['fallback_mode'] = match.group(1)
                if in_breakdown:
                    if 'Totals' in line:
                        total_mcrt_time = line.split()[-2]
                        total_mcrt_time = total_mcrt_time.replace(',', '')
                        stats['total_mcrt_time'] = float(total_mcrt_time)
                        stats['MCRT memory'] = get_gigabytes_from_size(line.split()[1], line.split()[2])
                        if 'total_render_prep_memory' in stats:
                            stats['MCRT memory'] = stats['MCRT memory'] - stats['total_render_prep_memory']
                        in_breakdown = False
                        continue
                    if '----' in line or 'Total' in line or 'Avg Time per' in line:
                        continue
                    tokens = line.split(' ')
                    stat_name = str()
                    get_stat_name = False
                    for t in tokens:
                        if get_stat_name:
                            if t == '':
                                get_stat_name = False
                            else:
                                stat_name = stat_name + t + ' '
                        if t == '|':
                            get_stat_name = True
                    stat_name = stat_name[0:-1]
                    time = tokens[-2]
                    time = time.replace(',', '')
                    stats[stat_name] = float(time)
                elif '- MCRT Time Breakdown -' in line:
                    in_breakdown = True
                    found_breakdown = True
                elif in_render_prep:
                    if 'Total render prep' in line:
                        stats['total_render_prep_time'] = get_seconds_from_time(line.split()[-1])
                        in_render_prep = False
                    else:
                        for stat in self.render_profile_chart.render_prep_stats:
                            if stat in line:
                                stats[stat] = get_seconds_from_time(line.split()[-1])
                elif '- Render Prep Stats -' in line:
                    in_render_prep = True
                elif in_render_prep_memory:
                    if 'Total memory' in line:
                        stats['total_render_prep_memory'] = get_gigabytes_from_size(line.split()[-2], line.split()[-1])
                        in_render_prep_memory = False
                    else:
                        for stat in self.render_profile_chart.memory_stats:
                            if stat in line:
                                stats[stat] = get_gigabytes_from_size(line.split()[-2], line.split()[-1])
                elif '- Memory Summary -' in line:
                    in_render_prep_memory = True
                elif 'Pixel samples' in line and 'Pixel samples sqrt' not in line:
                    pixel_samples = line.split('=')[1]
                    pixel_samples = pixel_samples.replace(',', '')
                    pixel_samples = pixel_samples.replace(' ', '')
                    pixel_samples = pixel_samples.replace('\n', '')
                    stats['pixel_samples'] = float(pixel_samples) / 1000000
                elif 'Host name' in line:
                    host_name = line.split('=')[1]
                    host_name = host_name.replace(' ', '')
                    host_name = host_name.replace('\n', '')
                    stats['host_name'] = host_name
                elif 'Wrote' in line:
                    if not found_wrote_line:
                        output_image = line.split()[1]
                        if output_image.endswith('Image.exr'):
                            stats['output_image'] = output_image
                            found_wrote_line = True
                elif '-- Callstack:' in line:
                    stats['crash'] = True

        if not found_breakdown:
            return None

        return stats

    def get_stats(self, test_name, week, log_file, log_type):
        cache_file_name = f"{test_name}_{week}_{log_type}.json"
        cache_file_path = os.path.join(self.cache_directory, cache_file_name)

        # If the cache file exists then just load it and return the stats
        if os.path.exists(cache_file_path) and self.use_cache:
            with open(cache_file_path) as f:
                try:
                    stats = json.load(f)
                except UnicodeDecodeError:
                    print(f"Error reading {cache_file_path}")
                    return None
            return stats

        # If the cache file doesn't exist then parse the logs for the stats
        if not os.path.exists(log_file):
            return None

        stats = self.parse_log_file(log_file)

        # Write json cache file with the stats data
        if not os.path.exists(os.path.dirname(cache_file_path)):
            os.makedirs(os.path.dirname(cache_file_path))

        with open(cache_file_path, "w") as f:
            json.dump(stats, f, indent=4)

        return stats


def main():
    parser = argparse.ArgumentParser(description="Visualizes render profile"
                                                 " statistics from log files"
                                                 " using charts")
    parser.add_argument('logs', nargs='*', help='optional list of log files to '
                                                'display as an alternative to the '
                                                'default render logs')
    args = parser.parse_args()

    app = QtWidgets.QApplication(sys.argv)
    app.setStyle(QtWidgets.QStyleFactory.create('Fusion'))
    MyWindow(args.logs)
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
