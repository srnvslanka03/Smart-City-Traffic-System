import os
import sys

from PyQt5.QtCore import Qt, QProcess
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QGroupBox,
    QSpinBox,
    QFormLayout,
    QGridLayout,
)


class TrafficUI(QWidget):
    def __init__(self):
        super().__init__()

        self.process = None  # QProcess for running simulation

        # Live stats state
        self.current_phase = ""
        self.lane_totals = {1: 0, 2: 0, 3: 0, 4: 0}
        self.total_vehicles = 0
        self.total_time = 0
        self.throughput = 0.0

        self.setWindowTitle("Adaptive Traffic Lights – Control Panel")
        self.resize(1100, 700)
        self._build_ui()
        self._apply_styles()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # Header
        title = QLabel("Adaptive Traffic Lights")
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))

        subtitle = QLabel(
            "Simulation dashboard – start / stop the Pygame simulation and watch live stats."
        )
        subtitle.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        header_box = QVBoxLayout()
        header_box.addWidget(title)
        header_box.addWidget(subtitle)

        header_widget = QWidget()
        header_widget.setLayout(header_box)

        main_layout.addWidget(header_widget)

        # Controls + Parameters row
        top_row = QHBoxLayout()
        top_row.setSpacing(16)

        # Controls group
        controls_group = QGroupBox("Simulation Controls")
        controls_layout = QVBoxLayout()
        controls_layout.setSpacing(12)

        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("Start Simulation")
        self.stop_btn = QPushButton("Stop Simulation")
        self.stop_btn.setEnabled(False)

        self.start_btn.clicked.connect(self.start_simulation)
        self.stop_btn.clicked.connect(self.stop_simulation)

        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.stop_btn)
        controls_layout.addLayout(btn_row)

        hint_lbl = QLabel(
            "When you click “Start Simulation”, a Pygame window will open.\n"
            "Use this panel to monitor the console output and performance."
        )
        hint_lbl.setWordWrap(True)
        controls_layout.addWidget(hint_lbl)

        controls_group.setLayout(controls_layout)

        # Parameters group (not yet wired into simulation constants, for future use)
        params_group = QGroupBox("Simulation Parameters")
        params_form = QFormLayout()
        params_form.setLabelAlignment(Qt.AlignLeft)

        self.sim_time_spin = QSpinBox()
        self.sim_time_spin.setRange(30, 10000)
        self.sim_time_spin.setValue(120)
        self.sim_time_spin.setSuffix(" s")

        self.min_green_spin = QSpinBox()
        self.min_green_spin.setRange(5, 120)
        self.min_green_spin.setValue(10)
        self.min_green_spin.setSuffix(" s")

        self.max_green_spin = QSpinBox()
        self.max_green_spin.setRange(10, 300)
        self.max_green_spin.setValue(60)
        self.max_green_spin.setSuffix(" s")

        params_form.addRow("Simulation time:", self.sim_time_spin)
        params_form.addRow("Minimum green time:", self.min_green_spin)
        params_form.addRow("Maximum green time:", self.max_green_spin)

        params_group.setLayout(params_form)

        top_row.addWidget(controls_group, stretch=2)
        top_row.addWidget(params_group, stretch=1)

        top_row_widget = QWidget()
        top_row_widget.setLayout(top_row)
        main_layout.addWidget(top_row_widget)

        # Stats row
        stats_group = QGroupBox("Live Statistics")
        stats_layout = QGridLayout()
        stats_layout.setSpacing(8)

        self.phase_label = QLabel("Current phase: —")

        self.lane_labels = {
            1: QLabel("Lane 1: 0 vehicles"),
            2: QLabel("Lane 2: 0 vehicles"),
            3: QLabel("Lane 3: 0 vehicles"),
            4: QLabel("Lane 4: 0 vehicles"),
        }

        self.total_label = QLabel("Total vehicles passed: 0")
        self.time_label = QLabel("Total time: 0 s")
        self.throughput_label = QLabel("Vehicles per unit time: 0.0")

        stats_layout.addWidget(self.phase_label, 0, 0, 1, 2)
        stats_layout.addWidget(self.lane_labels[1], 1, 0)
        stats_layout.addWidget(self.lane_labels[2], 1, 1)
        stats_layout.addWidget(self.lane_labels[3], 2, 0)
        stats_layout.addWidget(self.lane_labels[4], 2, 1)
        stats_layout.addWidget(self.total_label, 3, 0)
        stats_layout.addWidget(self.time_label, 3, 1)
        stats_layout.addWidget(self.throughput_label, 4, 0, 1, 2)

        stats_group.setLayout(stats_layout)
        main_layout.addWidget(stats_group)

        # Log output
        log_group = QGroupBox("Simulation Log")
        log_layout = QVBoxLayout()

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QTextEdit.NoWrap)
        self.log_view.setFont(QFont("Consolas", 10))
        self.log_view.setPlaceholderText(
            "Simulation output will appear here when you run it..."
        )

        log_layout.addWidget(self.log_view)
        log_group.setLayout(log_layout)

        main_layout.addWidget(log_group, stretch=1)

    def _apply_styles(self):
        # Simple modern dark theme
        self.setStyleSheet(
            """
            QWidget {
                background-color: #111827;
                color: #e5e7eb;
                font-family: "Segoe UI", sans-serif;
                font-size: 11pt;
            }
            QGroupBox {
                border: 1px solid #374151;
                border-radius: 8px;
                margin-top: 8px;
                padding: 12px;
                font-weight: 600;
                color: #f9fafb;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 4px;
            }
            QPushButton {
                background-color: #2563eb;
                color: #f9fafb;
                border: none;
                border-radius: 6px;
                padding: 8px 18px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
            QPushButton:disabled {
                background-color: #4b5563;
                color: #9ca3af;
            }
            QSpinBox {
                background-color: #111827;
                border: 1px solid #374151;
                border-radius: 4px;
                padding: 4px 6px;
                color: #e5e7eb;
            }
            QTextEdit {
                background-color: #020617;
                border-radius: 6px;
                border: 1px solid #374151;
            }
            """
        )

    def append_log(self, text: str):
        self.log_view.append(text.rstrip())
        self.log_view.verticalScrollBar().setValue(
            self.log_view.verticalScrollBar().maximum()
        )
        self._parse_for_stats(text)

    def _parse_for_stats(self, text: str):
        """
        Very lightweight parser that watches stdout lines to update the
        live statistics panel, based on the messages printed by simulation.py.
        """
        line = text.strip()
        if not line:
            return

        # Current phase from GREEN / YELLOW / RED status lines
        if "GREEN TS" in line or "YELLOW TS" in line or "RED TS" in line:
            # Show the whole status line as current phase
            self.current_phase = line
            self.phase_label.setText(f"Current phase: {self.current_phase}")

        # Lane-wise final counts
        if line.startswith("Lane ") and "Total:" in line:
            # Example: 'Lane 1: Total: 38'
            try:
                parts = line.split(":")
                lane_part = parts[0].strip()  # "Lane 1"
                total_part = parts[2].strip() if len(parts) > 2 else ""
                lane_num = int(lane_part.split()[1])
                total_val = int(total_part)
                self.lane_totals[lane_num] = total_val
                self.lane_labels[lane_num].setText(
                    f"Lane {lane_num}: {total_val} vehicles"
                )
            except Exception:
                pass

        # Total vehicles
        if line.startswith("Total vehicles passed"):
            # 'Total vehicles passed:  115'
            try:
                val_str = line.split(":")[1].strip()
                self.total_vehicles = int(float(val_str))
                self.total_label.setText(
                    f"Total vehicles passed: {self.total_vehicles}"
                )
            except Exception:
                pass

        # Total time
        if line.startswith("Total time passed"):
            # 'Total time passed:  120'
            try:
                val_str = line.split(":")[1].strip()
                self.total_time = int(float(val_str))
                self.time_label.setText(f"Total time: {self.total_time} s")
            except Exception:
                pass

        # Throughput
        if line.startswith("No. of vehicles passed per unit time"):
            # 'No. of vehicles passed per unit time:  0.95...'
            try:
                val_str = line.split(":")[1].strip()
                self.throughput = float(val_str)
                self.throughput_label.setText(
                    f"Vehicles per unit time: {self.throughput:.3f}"
                )
            except Exception:
                pass

    def start_simulation(self):
        if self.process is not None:
            return

        # Clear previous log
        self.log_view.clear()
        self.append_log("Starting simulation...\n")

        self.process = QProcess(self)

        # Pass parameters via environment variables so simulation.py can read them
        env = self.process.processEnvironment()
        sim_time = str(self.sim_time_spin.value())
        min_green = str(self.min_green_spin.value())
        max_green = str(self.max_green_spin.value())
        env.insert("SIM_TIME", sim_time)
        env.insert("MIN_GREEN_TIME", min_green)
        env.insert("MAX_GREEN_TIME", max_green)
        self.process.setProcessEnvironment(env)

        # Use the current Python interpreter
        python_executable = sys.executable or "python"

        # Ensure working directory is project root (where simulation.py lives)
        project_root = os.path.dirname(os.path.abspath(__file__))
        self.process.setWorkingDirectory(project_root)

        # NOTE: For now, parameters are not wired into simulation.py.
        # We simply run the existing script.
        self.process.setProgram(python_executable)
        self.process.setArguments(["simulation.py"])

        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.simulation_finished)

        self.process.start()

        if not self.process.waitForStarted(3000):
            self.append_log("Failed to start simulation process.\n")
            self.process = None
            return

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def stop_simulation(self):
        if self.process is None:
            return

        self.append_log("\nStopping simulation...\n")
        self.process.kill()
        self.process.waitForFinished(2000)
        self.process = None

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def handle_stdout(self):
        if self.process is None:
            return
        data = self.process.readAllStandardOutput()
        text = bytes(data).decode(errors="ignore")
        for line in text.splitlines():
            self.append_log(line)

    def handle_stderr(self):
        if self.process is None:
            return
        data = self.process.readAllStandardError()
        text = bytes(data).decode(errors="ignore")
        for line in text.splitlines():
            self.append_log(f"[error] {line}")

    def simulation_finished(self):
        self.append_log("\nSimulation finished.\n")
        self.process = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)


def main():
    app = QApplication(sys.argv)
    window = TrafficUI()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()


