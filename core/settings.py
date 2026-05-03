import sys
import os
import winreg
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QGroupBox, QHBoxLayout,
    QLabel, QPlainTextEdit, QPushButton, QSizePolicy, QSpacerItem, QTabWidget, QTextEdit,
    QVBoxLayout, QWidget, QSpinBox)
import datetime
import requests
import core.config_manager as Config
from core import log_maker

import BlurWindow.blurWindow as blurWindow

log = log_maker.logger()

ABOUT_TEXT = f"&&PROJNAME&&\n版本 &&VERSION&&\n\n&&PROJNAME&& 是开源软件，依据 &&LICENSE&& 开源协议管理源代码及其二进制文件分发\n\n&&CONTRIBUTION&&\n\n&&UPDINFO&&"
PROJ_NAME = "MikaDesktop"

LICENSE = "BSD 3-Clause License"
CONTRIBUTION = f"有许多人为 {PROJ_NAME} 做出了贡献，访问 {PROJ_NAME} 的 GitHub 仓库以获取更多信息。"

NO_UPD_TEXT = f"已为最新版本。"
NEW_UPD_TEXT = f"存在新版本"
ERROR_UPD_TEXT = f"检查更新失败："

BASE_CHECK_UPD_URL = "https://api.github.com/repos/KazumaRimatsu/MikaDesktop"
LATEST_CHECK_UPD_URL = f"{BASE_CHECK_UPD_URL}/activity?per_page=1"
RELEASE_CHECK_UPD_URL = f"{BASE_CHECK_UPD_URL}/releases"

AUTOSTART_KEY = "MikaDesktop"


class SettingsUI(QDialog):
    def __init__(self, version: str = "unknown", is_nuitka: bool = False,
                 config_path: str = None, on_save_callback=None):
        super().__init__()
        self.version = version
        self.is_nuitka = is_nuitka
        self.config_path = config_path
        self.on_save_callback = on_save_callback
        self.config_data = {}
        self.load_config_data()
        self.init_ui()

    def load_config_data(self):
        if self.config_path and os.path.exists(self.config_path):
            self.config_data = Config.load_config(self.config_path)
        else:
            self.config_data = Config.DEFAULT_CONFIG.copy()

    def init_ui(self):
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(640, 480)
        self.setWindowTitle(f"{PROJ_NAME} - 设置")
        self.verticalLayout_3 = QVBoxLayout(self)
        self.tabWidget = QTabWidget(self)

        self.general = QWidget()
        self.verticalLayout_5 = QVBoxLayout(self.general)

        self.enable_autostart = QCheckBox(self.general)
        self.verticalLayout_5.addWidget(self.enable_autostart)

        self.enable_debug = QCheckBox(self.general)
        self.verticalLayout_5.addWidget(self.enable_debug)

        self.verticalSpacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        self.verticalLayout_5.addItem(self.verticalSpacer)

        self.tabWidget.addTab(self.general, "")

        self.dock = QWidget()

        self.except_apps = QGroupBox(self.dock)
        self.verticalLayout = QVBoxLayout(self.except_apps)

        self.except_apps_tips_label = QLabel(self.except_apps)
        self.verticalLayout.addWidget(self.except_apps_tips_label)

        self.plainTextEdit = QPlainTextEdit(self.except_apps)
        self.plainTextEdit.setStyleSheet(u"background: #EEEEEE")
        self.plainTextEdit.setDocumentTitle(u"")
        self.plainTextEdit.setPlaceholderText(u"例如：notepad.exe\\nmsedge.exe")
        self.verticalLayout.addWidget(self.plainTextEdit)


        #self.verticalLayout_2.addWidget(self.except_apps)

        self.tabWidget.addTab(self.dock, "")

        self.notify = QWidget()
        self.notify_layout = QVBoxLayout(self.notify)

        self.notify_group = QGroupBox(self.notify)
        self.notify_group_layout = QVBoxLayout(self.notify_group)

        self.notify_timeout_label = QLabel(self.notify_group)
        self.notify_group_layout.addWidget(self.notify_timeout_label)

        self.notify_timeout_spin = QSpinBox(self.notify_group)
        self.notify_timeout_spin.setRange(0, 60)
        self.notify_timeout_spin.setSuffix(u" 秒")
        self.notify_timeout_spin.setSpecialValueText(u"不限时")
        self.notify_group_layout.addWidget(self.notify_timeout_spin)

        self.notify_group_layout.addItem(
            QSpacerItem(20, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        )

        self.notify_desc_label = QLabel(self.notify_group)
        self.notify_desc_label.setWordWrap(True)
        self.notify_group_layout.addWidget(self.notify_desc_label)

        self.notify_layout.addWidget(self.notify_group)

        self.notify_verticalSpacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        self.notify_layout.addItem(self.notify_verticalSpacer)

        self.tabWidget.addTab(self.notify, "")

        self.about = QWidget()
        self.verticalLayout_4 = QVBoxLayout(self.about)
        self.about_text = QTextEdit(self.about)
        self.about_text.setDocumentTitle(u"")
        self.about_text.setAcceptRichText(True)
        self.about_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByKeyboard|Qt.TextInteractionFlag.TextSelectableByMouse)

        self.verticalLayout_4.addWidget(self.about_text)

        self.horizontalLayout_3 = QHBoxLayout()
        self.check_upd_button = QPushButton(self.about)
        self.check_upd_button.setStyleSheet(u"QPushButton {\n"
"                background-color: #DDDDDD;\n"
"                color: black;\n"
"                border: none;\n"
"                border-radius: 5px;\n"
"                padding: 12px;\n"
"                font-size: 15px;\n"
"				font-family: 'Microsoft YaHei UI';\n"
"				font-weight: Bold;\n"
"                min-height: 20px;\n"
"            }\n"
"            QPushButton:hover {\n"
"                background-color: #CCCCCC;\n"
"            }\n"
"            QPushButton:pressed {\n"
"                background-color: #BBBBBB;\n"
"            }")

        self.horizontalLayout_3.addWidget(self.check_upd_button)

        self.horizontalSpacer_2 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.horizontalLayout_3.addItem(self.horizontalSpacer_2)

        self.verticalLayout_4.addLayout(self.horizontalLayout_3)

        self.tabWidget.addTab(self.about, "")

        self.verticalLayout_3.addWidget(self.tabWidget)

        self.horizontalLayout = QHBoxLayout()

        self.status_label = QLabel(self)
        self.horizontalLayout.addWidget(self.status_label)

        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.horizontalLayout.addItem(self.horizontalSpacer)
        self.save_button = QPushButton(self)
        self.save_button.setStyleSheet(u"QPushButton {\n"
"                background-color: #00c0aa;\n"
"                color: white;\n"
"                border: none;\n"
"                border-radius: 5px;\n"
"                padding: 12px;\n"
"                font-size: 15px;\n"
"				font-family: 'Microsoft YaHei UI';\n"
"				font-weight: Bold;\n"
"                min-height: 20px;\n"
"            }\n"
"            QPushButton:hover {\n"
"                background-color: #00A894;\n"
"            }\n"
"            QPushButton:pressed {\n"
"                background-color: #008979;\n"
"            }")

        self.horizontalLayout.addWidget(self.save_button)

        self.verticalLayout_3.addLayout(self.horizontalLayout)

        self.enable_autostart.setText(u"开机时自动运行")
        self.enable_debug.setText(u"启用debug日志")
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.general), u"通用")
        self.except_apps.setTitle(u"排除的应用")
        self.except_apps_tips_label.setText(u"键入进程名（每行一个，无需.exe后缀）")
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.dock), u"Dock")
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.notify), u"通知")
        self.notify_group.setTitle(u"通知选项")
        self.notify_timeout_label.setText(u"默认通知超时时间：")
        self.notify_desc_label.setText(u"通知使用 HTTP 服务器在 127.0.0.2:8848 监听。\n支持 title、context、level、type、timelimit 等参数。\n交互式通知使用 '+' 分隔选项，最多 4 个。")
        self.about_text.setText(ABOUT_TEXT)
        self.check_upd_button.setText(u"检查更新")
        self.check_upd_button.clicked.connect(self.check_update)
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.about), u"关于")
        self.status_label.setText(u"就绪")
        self.save_button.setText(u"  保存  ")
        self.tabWidget.setCurrentIndex(1)

        self.save_button.clicked.connect(self.save_settings)

        self.load_settings_to_ui()
        self.upd_about_text()

        QTimer.singleShot(100, self.apply_blur_effect)

        self.upd_status("就绪")

    def load_settings_to_ui(self):
        debug_enabled = self.config_data.get('debug', False)
        self.enable_debug.setChecked(debug_enabled)

        dock_config = self.config_data.get('dock', {})

        except_list = dock_config.get('except_processes', [])
        self.plainTextEdit.setPlainText('\n'.join(except_list))

        notify_config = self.config_data.get('notify', {})
        timeout = notify_config.get('default_timeout', 0)
        self.notify_timeout_spin.setValue(timeout)

        self.check_autostart_status()

    def check_autostart_status(self):
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_READ
            )
            try:
                value, _ = winreg.QueryValueEx(key, AUTOSTART_KEY)
                self.enable_autostart.setChecked(True)
            except FileNotFoundError:
                self.enable_autostart.setChecked(False)
            winreg.CloseKey(key)
        except Exception as e:
            log.error(f"读取自启动注册表失败: {e}")
            self.enable_autostart.setChecked(False)

    def set_autostart(self, enable: bool):
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE
            )
            if enable:
                exe_path = sys.executable
                if not self.is_nuitka:
                    script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dock.py")
                    if os.path.exists(script_path):
                        value = f'"{exe_path}" "{script_path}"'
                    else:
                        value = f'"{exe_path}"'
                else:
                    value = f'"{exe_path}"'
                winreg.SetValueEx(key, AUTOSTART_KEY, 0, winreg.REG_SZ, value)
                log.info(f"已添加自启动: {value}")
            else:
                try:
                    winreg.DeleteValue(key, AUTOSTART_KEY)
                    log.info("已移除自启动")
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            log.error(f"设置自启动失败: {e}")

    def collect_settings(self):
        dock_config = self.config_data.get('dock', {})
        dock_config['except_processes'] = [
            line.strip() for line in self.plainTextEdit.toPlainText().split('\n') if line.strip()
        ]

        notify_config = self.config_data.get('notify', {})
        notify_config['default_timeout'] = self.notify_timeout_spin.value()

        self.config_data['debug'] = self.enable_debug.isChecked()
        self.config_data['dock'] = dock_config
        self.config_data['notify'] = notify_config

    def save_settings(self):
        try:
            self.collect_settings()

            if self.config_path:
                Config.save_config(self.config_path, self.config_data)

            self.set_autostart(self.enable_autostart.isChecked())

            if self.enable_debug.isChecked():
                log.enable_debug()
            else:
                log.disable_debug()

            self.upd_status(u"设置已保存", "success")

            if self.on_save_callback:
                self.on_save_callback(self.config_data)

            log.info("设置已保存")
        except Exception as e:
            self.upd_status(f"保存设置失败: {e}", "error")
            log.error(f"保存设置失败: {e}")

    def upd_status(self, text: str, status_type: str = None):
        if status_type == "success":
            self.status_label.setStyleSheet(u"color: #53b482;")
            self.status_label.setText(text)
        elif status_type == "error":
            self.status_label.setStyleSheet(u"color: #ff0000;")
            self.status_label.setText(text)
        elif status_type == "warning":
            self.status_label.setStyleSheet(u"color: #ff9900;")
            self.status_label.setText(text)
        else:
            self.status_label.setStyleSheet(u"color: #0000FF;")
            self.status_label.setText(text)

    def check_update(self):
        if self.is_nuitka:
            self.upd_status("编译环境，检查Release")
            release_req = requests.get(RELEASE_CHECK_UPD_URL)
            if release_req.status_code != 200:
                self.upd_status(f"检查更新失败", "error")
                self.upd_about_text(upd_text=f"{ERROR_UPD_TEXT}{release_req.status_code}", contribution=False)
                return
            release_data = list(release_req.text)
            if len(release_data) == 0:
                self.upd_status(f"没有Releases", "warning")
                self.upd_about_text(upd_text=NO_UPD_TEXT, contribution=False)
                return
        else:
            self.upd_status("非编译环境，检查最近推送")
            latest_req = requests.get(LATEST_CHECK_UPD_URL)
            if latest_req.status_code != 200:
                self.upd_status(f"检查更新失败", "error")
                self.upd_about_text(upd_text=f"{ERROR_UPD_TEXT}{latest_req.status_code}", contribution=False)
                return
            latest_data = latest_req.json()
            if len(latest_data) == 0:
                self.upd_status(f"没有latest Builds", "warning")
                self.upd_about_text(upd_text=NO_UPD_TEXT, contribution=False)
                return
            if datetime.datetime.strptime(latest_data[0]["timestamp"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp() > datetime.datetime.timestamp(datetime.datetime.now()):
                self.upd_status(f"存在新版本", "success")
                self.upd_about_text(upd_text=NEW_UPD_TEXT, contribution=False)
                return
            else:
                self.upd_status(f"暂无新版本", "success")
                self.upd_about_text(upd_text=NO_UPD_TEXT, contribution=False)
                return

    def upd_about_text(self, upd_text: str = "", contribution: bool = False):
        self.about_text.setText(ABOUT_TEXT.replace("&&VERSION&&", self.version)
            .replace("&&PROJNAME&&", PROJ_NAME)
            .replace("&&LICENSE&&", LICENSE)
            .replace("&&CONTRIBUTION&&", CONTRIBUTION if contribution else "")
            .replace("&&UPDINFO&&", upd_text))
        
    def apply_blur_effect(self):
        """应用窗口模糊效果"""
        try:
			# 使用GlobalBlur函数为窗口添加模糊效果
            blurWindow.blur(self.winId(), hexColor=False, Dark=True)
        except Exception as e:  
            pass  # 静默失败，不影响对话框功能



if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SettingsUI(is_nuitka=False, config_path=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "settings.json"))
    window.show()
    sys.exit(app.exec())
