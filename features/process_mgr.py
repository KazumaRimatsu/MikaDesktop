import os
import sys
import psutil
import threading
from PySide6.QtWidgets import (
    QApplication, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit, QMessageBox, QPushButton, QLabel, QStyle,
    QAbstractItemView, QMenu, QCheckBox, QDialog
)
from PySide6.QtCore import Qt, QThread, Signal

window = None


class ProcessCollectorWorker(QThread):
    data_collected = Signal(list)
    errorOccurred = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._name = "process_mgr"
        self._paused = False
        self._pause_lock = threading.Lock()
        self._trigger = threading.Event()

    def get_name(self):
        return self._name

    def pause(self):
        with self._pause_lock:
            self._paused = True

    def resume(self):
        with self._pause_lock:
            self._paused = False
        self._trigger.set()

    def is_paused(self):
        with self._pause_lock:
            return self._paused

    def trigger(self):
        self._trigger.set()

    def run(self):
        while not self.isInterruptionRequested():
            with self._pause_lock:
                paused = self._paused
            if paused:
                self._trigger.wait(1)
                self._trigger.clear()
                continue

            try:
                raw = self._collect()
                self.data_collected.emit(raw)
            except Exception as e:
                self.errorOccurred.emit(str(e))

            self._trigger.wait(3)
            self._trigger.clear()

    def _collect(self):
        results = []
        for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'exe']):
            try:
                with proc.oneshot():
                    info = proc.info
                    pid = info['pid']
                    if pid == 0:
                        continue
                    name = info['name'] or "未知"
                    mem = info['memory_info']
                    mem_rss = mem.rss if mem else 0
                    exe = info['exe'] or ""
                    try:
                        cpu = proc.cpu_percent(interval=0.0)
                    except Exception:
                        cpu = 0.0
                results.append({
                    'name': name,
                    'pid': pid,
                    'cpu': cpu,
                    'memory': mem_rss,
                    'exe': exe,
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        results.sort(key=lambda x: x['memory'], reverse=True)
        return results


class NumericTableItem(QTableWidgetItem):
    def __init__(self, text, sort_value):
        super().__init__(text)
        self._sort_value = sort_value

    def __lt__(self, other):
        if isinstance(other, NumericTableItem):
            return self._sort_value < other._sort_value
        return super().__lt__(other)


class ProcessTableWidget(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_table()

    def setup_table(self):
        headers = ["进程名称", "PID", "CPU(%)", "内存（MB）"]
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.horizontalHeader().setSectionsClickable(True)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.verticalHeader().setVisible(False)
        self.setColumnWidth(0, 200)
        self.setColumnWidth(1, 80)
        self.setColumnWidth(2, 120)
        self.setColumnWidth(3, 120)

    def format_memory(self, bytes_val):
        if bytes_val < 0:
            return "N/A"
        return f"{bytes_val / 1024. / 1024:.1f} MB"


class ProcessManagerWindow(QDialog):
    def __init__(self, collector=None):
        super().__init__()
        self.setWindowTitle("进程管理器")
        self.resize(600, 600)

        self.process_data = []
        self.current_filter = ""
        self.collector = collector

        self.setup_ui()

        if self.collector is not None:
            self.collector.data_collected.connect(self.on_data_collected)

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)

        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(4)

        refresh_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        refresh_btn = QPushButton(refresh_icon, "刷新")
        refresh_btn.setShortcut("F5")
        refresh_btn.clicked.connect(self._manual_refresh)
        toolbar_layout.addWidget(refresh_btn)

        kill_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DialogCloseButton)
        self.kill_btn = QPushButton(kill_icon, "结束进程")
        self.kill_btn.setShortcut("Delete")
        self.kill_btn.clicked.connect(self.kill_selected_process)
        toolbar_layout.addWidget(self.kill_btn)

        toolbar_layout.addSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索进程...")
        self.search_input.setMaximumWidth(250)
        self.search_input.textChanged.connect(self.on_search_text_changed)
        toolbar_layout.addWidget(self.search_input)

        toolbar_layout.addSpacing(8)

        self.auto_refresh_check = QCheckBox("自动刷新")
        self.auto_refresh_check.setChecked(True)
        self.auto_refresh_check.toggled.connect(self._on_auto_refresh_toggled)
        toolbar_layout.addWidget(self.auto_refresh_check)

        toolbar_layout.addStretch()
        main_layout.addLayout(toolbar_layout)

        self.table = ProcessTableWidget()
        main_layout.addWidget(self.table)

        self.status_label = QLabel()
        main_layout.addWidget(self.status_label)

    def _manual_refresh(self):
        if self.collector is not None:
            self.collector.trigger()

    def _on_auto_refresh_toggled(self, checked):
        if self.collector is not None:
            if checked:
                self.collector.resume()
            else:
                self.collector.pause()

    def on_data_collected(self, raw):
        self.process_data = raw
        self.apply_filter()

    def apply_filter(self):
        self.table.setSortingEnabled(False)

        filtered = self.process_data
        keyword = self.current_filter.strip().lower()
        if keyword:
            filtered = [p for p in filtered if keyword in p['name'].lower() or keyword in str(p['pid'])]

        existing_count = self.table.rowCount()
        new_count = len(filtered)
        if new_count != existing_count:
            self.table.setRowCount(new_count)

        for row, proc in enumerate(filtered):
            if row < existing_count and self.table.item(row, 0) is not None:
                existing_pid = self.table.item(row, 1).text()
                if existing_pid == str(proc['pid']):
                    cpu_text = f"{proc['cpu']:.2f}%"
                    mem_text = self.table.format_memory(proc['memory'])
                    self.table.item(row, 0).setText(proc['name'])
                    self.table.item(row, 0).setToolTip(proc['exe'])
                    pid_item = self.table.item(row, 1)
                    pid_item.setText(str(proc['pid']))
                    pid_item._sort_value = proc['pid']
                    cpu_item = self.table.item(row, 2)
                    cpu_item.setText(cpu_text)
                    cpu_item._sort_value = proc['cpu']
                    mem_item = self.table.item(row, 3)
                    mem_item.setText(mem_text)
                    mem_item._sort_value = proc['memory']
                    continue

            name_item = QTableWidgetItem(proc['name'])
            name_item.setToolTip(proc['exe'])
            self.table.setItem(row, 0, name_item)

            pid_item = NumericTableItem(str(proc['pid']), proc['pid'])
            pid_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 1, pid_item)

            cpu_text = f"{proc['cpu']:.2f}%"
            cpu_item = NumericTableItem(cpu_text, proc['cpu'])
            cpu_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 2, cpu_item)

            mem_text = self.table.format_memory(proc['memory'])
            mem_item = NumericTableItem(mem_text, proc['memory'])
            mem_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 3, mem_item)

        if new_count < existing_count:
            for row in range(new_count, existing_count):
                for col in range(4):
                    self.table.setItem(row, col, None)

        self.table.setSortingEnabled(True)

        total = len(self.process_data)
        self.status_label.setText(f"{total} 个进程")

    def on_search_text_changed(self, text):
        self.current_filter = text
        self.apply_filter()

    def kill_selected_process(self):
        rows = set()
        for idx in self.table.selectedIndexes():
            rows.add(idx.row())
        if not rows:
            QMessageBox.information(self, "提示", "请先选择一个进程")
            return

        targets = []
        for row in rows:
            name = self.table.item(row, 0).text()
            pid_text = self.table.item(row, 1).text()
            targets.append((name, int(pid_text)))

        if len(targets) == 1:
            name, pid = targets[0]
            if pid <= 0:
                QMessageBox.warning(self, "警告", "无法结束系统空闲进程")
                return
            if pid == os.getpid():
                QMessageBox.warning(self, "警告", "无法结束本程序自身")
                return
            reply = QMessageBox.question(
                self, "确认结束进程",
                f"确定要结束进程 （及其所有子进程） \"{name}\" (PID: {pid})？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            self._do_kill(pid)
        else:
            names_str = "\n".join([f"{n} (PID: {p})" for n, p in targets])
            reply = QMessageBox.question(
                self, "确认结束多个进程",
                f"确定要结束以下 {len(targets)} 个进程（及其所有子进程）？\n{names_str}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            for _, pid in targets:
                self._do_kill(pid)

    def _do_kill(self, pid):
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            self.status_label.setText(f"已发送终止信号给 PID {pid}")
        except psutil.NoSuchProcess:
            QMessageBox.information(self, "进程不存在", f"PID {pid} 的进程已不存在")
        except psutil.AccessDenied:
            QMessageBox.warning(self, f"无法结束 PID {pid} 的进程", "权限需要提升")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"结束进程时出错: {e}")

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        kill_action = menu.addAction("结束进程")
        kill_action.triggered.connect(self.kill_selected_process)
        menu.exec(event.globalPos())

    def closeEvent(self, event):
        super().closeEvent(event)


def main():
    global window
    app = QApplication(sys.argv)
    app.setApplicationName("进程管理器")

    collector = ProcessCollectorWorker()
    collector.data_collected.connect(_on_data_collected)

    window = ProcessManagerWindow(collector=collector)
    window.show()

    collector.start()

    sys.exit(app.exec())


def _on_data_collected(raw):
    global window
    if window is not None:
        window.on_data_collected(raw)


def run(collector=None):
    global window
    window = ProcessManagerWindow(collector=collector)
    window.show()


def quit():
    if window is not None:
        window.close()


if __name__ == "__main__":
    main()
