import os
import sys
import yaml

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QFormLayout,
    QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit, QCheckBox,
    QPushButton, QGroupBox, QListWidget, QListWidgetItem,
    QHBoxLayout, QTextEdit, QLabel, QSplitter, QScrollArea
)
from PySide6.QtCore import Qt, Slot
from ui.executor import BotWorker  # убедитесь, что путь корректный

class SettingsWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Настройки торгового бота")
        self.settings_file = os.path.join(
            os.path.dirname(__file__),
            '..', 'config', 'settings.yaml'
        )

        # Bot-воркер
        self.worker = BotWorker()
        self.worker.log_signal.connect(self.append_log)
        self.worker.price_signal.connect(self.update_price)
        self.worker.slippage_signal.connect(self.update_slippage)
        self.worker.finished.connect(lambda: self.append_log("❌ Бот остановлен"))

        # — Левое окно: логи и управление —
        left = QWidget()
        left_l = QVBoxLayout(left)
        btn_l = QHBoxLayout()
        self.start_button = QPushButton("▶️ Запустить бота")
        self.stop_button  = QPushButton("⏹️ Остановить бота")
        self.price_label     = QLabel("Цена: —")
        self.slippage_label  = QLabel("Проскальз.: —")
        btn_l.addWidget(self.start_button)
        btn_l.addWidget(self.stop_button)
        btn_l.addStretch()
        btn_l.addWidget(self.price_label)
        btn_l.addSpacing(20)
        btn_l.addWidget(self.slippage_label)
        left_l.addLayout(btn_l)

        self.logs_view = QTextEdit()
        self.logs_view.setReadOnly(True)
        self.logs_view.setLineWrapMode(QTextEdit.NoWrap)
        left_l.addWidget(self.logs_view, 1)

        self.start_button.clicked.connect(self.start_bot)
        self.stop_button.clicked.connect(self.stop_bot)
        self.worker.slippage_signal.connect(self.update_slippage)

        # — Правое окно: настройки —
        right = QWidget()
        right_l = QVBoxLayout(right)

        # Глобальные настройки
        self.global_group = QGroupBox("Глобальные настройки")
        gl = QFormLayout(self.global_group)

        self.mode                  = QComboBox(); self.mode.addItems(["SIMPLE","RSI","MRC","ZONE","COMBO"])
        self.mode.currentTextChanged.connect(self.on_mode_changed)
        self.leverage              = QSpinBox();   self.leverage.setRange(1,125)
        self.trade_direction       = QComboBox();  self.trade_direction.addItems(["LONG","SHORT","BOTH"])
        self.entry_step_percent    = QDoubleSpinBox(); self.entry_step_percent.setDecimals(3); self.entry_step_percent.setSingleStep(0.1)
        self.step_multiplier       = QDoubleSpinBox(); self.step_multiplier.setDecimals(2); self.step_multiplier.setSingleStep(0.1)
        self.min_step_percent      = QDoubleSpinBox(); self.min_step_percent.setDecimals(3); self.min_step_percent.setSingleStep(0.1)
        self.tp_percent            = QDoubleSpinBox(); self.tp_percent.setDecimals(2); self.tp_percent.setSingleStep(0.1)
        self.initial_order_percent = QDoubleSpinBox(); self.initial_order_percent.setDecimals(2); self.initial_order_percent.setSingleStep(0.1)
        self.close_threshold_percent = QDoubleSpinBox(); self.close_threshold_percent.setDecimals(2); self.close_threshold_percent.setSingleStep(0.1)
        self.partial_close_percent = QDoubleSpinBox(); self.partial_close_percent.setDecimals(1); self.partial_close_percent.setSingleStep(1.0); self.partial_close_percent.setRange(0.0, 100.0)
        # Новые поля
        self.commission_percent    = QDoubleSpinBox(); self.commission_percent.setDecimals(3); self.commission_percent.setSuffix(" %")
        self.slippage_percent      = QDoubleSpinBox(); self.slippage_percent.setDecimals(3); self.slippage_percent.setSuffix(" %")
        self.lot_multiplier        = QDoubleSpinBox(); self.lot_multiplier.setDecimals(2); self.lot_multiplier.setSingleStep(0.1)
        self.avg_mode              = QComboBox(); self.avg_mode.addItems(["martingale","pyramiding","mirror"])
        self.max_orders            = QSpinBox(); self.max_orders.setRange(1,1000)
        self.log_time_format       = QLineEdit("%d/%m/%Y %H:%M:%S.%f")
        self.ping_display          = QCheckBox("Отображать ping")
        self.slippage_display      = QCheckBox("Отображать проскальзывание")

        fields = [
            ("Режим (mode):", self.mode),
            ("Плечо:", self.leverage),
            ("Направление:", self.trade_direction),
            ("Шаг входа:", self.entry_step_percent),
            ("Множитель шага:", self.step_multiplier),
            ("Мин. шаг:", self.min_step_percent),
            ("TP %:", self.tp_percent),
            ("Первый ордер %:", self.initial_order_percent),
            ("Порог сальдо %:", self.close_threshold_percent),
            ("Комиссия %:", self.commission_percent),
            ("Проскальзывание %:", self.slippage_percent),
            ("Множитель лота:", self.lot_multiplier),
            ("Мод усреднения:", self.avg_mode),
            ("Максимальный ордер:", self.max_orders),
            ("Формат логов:", self.log_time_format),
        ]
        for label, widget in fields:
            gl.addRow(label, widget)
        gl.addRow("Частичное закрытие %:", self.partial_close_percent)
        gl.addRow(self.ping_display)
        gl.addRow(self.slippage_display)
        right_l.addWidget(self.global_group)

        # RSI
        self.rsi_group = QGroupBox("Параметры RSI")
        rg = QFormLayout(self.rsi_group)
        self.rsi_period    = QSpinBox(); self.rsi_period.setRange(1,100)
        self.rsi_upper     = QSpinBox(); self.rsi_upper.setRange(1,100)
        self.rsi_lower     = QSpinBox(); self.rsi_lower.setRange(1,100)
        self.rsi_threshold = QSpinBox(); self.rsi_threshold.setRange(1,50)
        rg.addRow("Период:", self.rsi_period)
        rg.addRow("Верхний порог:", self.rsi_upper)
        rg.addRow("Нижний порог:", self.rsi_lower)
        rg.addRow("Порог сигнала:", self.rsi_threshold)
        right_l.addWidget(self.rsi_group)

        # MRC
        self.mrc_group = QGroupBox("Параметры MRC")
        mg = QFormLayout(self.mrc_group)
        levels = ["1","2","3","4","5","2.1","3.1","4.1","5.1"]
        self.mrc_entry_level       = QComboBox(); self.mrc_entry_level.addItems(levels)
        self.mrc_exit_level        = QComboBox(); self.mrc_exit_level.addItems(levels)
        self.mrc_entry_candle_type = QComboBox(); self.mrc_entry_candle_type.addItems(["cross","reverse"])
        self.mrc_exit_candle_type  = QComboBox(); self.mrc_exit_candle_type.addItems(["cross","reverse"])
        mg.addRow("Уровень входа:",   self.mrc_entry_level)
        mg.addRow("Уровень выхода:",  self.mrc_exit_level)
        mg.addRow("Тип свечи входа:",  self.mrc_entry_candle_type)
        mg.addRow("Тип свечи выхода:", self.mrc_exit_candle_type)
        right_l.addWidget(self.mrc_group)

        # Zone
        self.zone_group = QGroupBox("Параметры Zone")
        zg = QFormLayout(self.zone_group)
        # 1) режим зоны
        self.zone_mode  = QComboBox(); self.zone_mode .addItems(["1","2","3"])
        # 2) уровень (для режимов 1 и 3)
        self.zone_level = QComboBox(); self.zone_level.addItems(levels)
        # 3) зоны (для режима 2)
        self.zone_entry_zones = QListWidget()
        self.zone_entry_zones.setSelectionMode(QListWidget.MultiSelection)
        for lvl in levels:
            QListWidgetItem(lvl, self.zone_entry_zones)
        # 4) тип свечи
        self.zone_candle_type = QComboBox(); self.zone_candle_type.addItems(["cross","reverse"])

        zg.addRow("Режим зоны:",         self.zone_mode)
        zg.addRow("Уровень зоны:",       self.zone_level)
        zg.addRow("Выбор зон (Ctrl+клик):", self.zone_entry_zones)
        zg.addRow("Тип свечи входа:",    self.zone_candle_type)
        right_l.addWidget(self.zone_group)

        # Сохранить
        self.save_button = QPushButton("💾 Сохранить и применить")
        self.save_button.clicked.connect(self.save_settings)
        right_l.addWidget(self.save_button, alignment=Qt.AlignRight)

        # Сплиттер
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left)

        # оборачиваем правую панель в QScrollArea, чтобы можно было скроллить при COMBO
        scroll = QScrollArea()
        scroll.setWidget(right)
        scroll.setWidgetResizable(True)
        # при желании ограничим минимальную ширину
        scroll.setMinimumWidth(350)

        splitter.addWidget(scroll)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        self.setCentralWidget(splitter)

    
        # Загрузить и показать нужные группы
        self.zone_mode.currentTextChanged.connect(self.on_zone_mode_changed)
        # Загрузка и первичная отрисовка
        self.load_settings()
        self.on_mode_changed(self.mode.currentText())
        self.on_zone_mode_changed(self.zone_mode.currentText())


    @Slot()
    def start_bot(self):
        cfg = self.build_settings()
        self.append_log("▶️ Стартуем бота с текущими настройками")
        self.worker.set_settings(cfg)
        self.worker.start()

    @Slot()
    def stop_bot(self):
        self.worker.stop()

    def append_log(self, line: str):
        self.logs_view.append(line)

    def update_price(self, price: float):
        self.price_label.setText(f"Цена: {price:.2f}")
    @Slot(float)
    def update_slippage(self, sl: float):
        # sl уже в процентах
       self.slippage_label.setText(f"Проскальз.: {sl:.2f}%")

    def on_mode_changed(self, mode: str):
        mapping = {
            "SIMPLE": [],
            "RSI":    [self.rsi_group],
            "MRC":    [self.mrc_group],
            "ZONE":   [self.zone_group],
            "COMBO":  [self.rsi_group, self.mrc_group, self.zone_group],
        }
        for grp in (self.rsi_group, self.mrc_group, self.zone_group):
            grp.setVisible(False)
        for grp in mapping.get(mode, []):
            grp.setVisible(True)
    def on_zone_mode_changed(self, mode: str):
        # режим 2 — symmetric: показываем многострочный список, скрываем одиночный
        if mode == "2":
            self.zone_entry_zones.show()
            self.zone_level.hide()
        else:
            self.zone_entry_zones.hide()
            self.zone_level.show()
    def load_settings(self):
        if not os.path.exists(self.settings_file):
            return
        with open(self.settings_file, 'r') as f:
            cfg = yaml.safe_load(f) or {}

        g = cfg.get("global", {})
        self.mode.setCurrentText(cfg.get("mode","SIMPLE"))
        self.leverage.setValue(g.get("leverage",10))
        self.trade_direction.setCurrentText(cfg.get("trade_direction","BOTH"))
        self.entry_step_percent.setValue(g.get("step_percent",0.4))
        self.step_multiplier.setValue(g.get("step_multiplier",1.0))
        self.min_step_percent.setValue(g.get("min_step_percent",0.2))
        self.tp_percent.setValue(g.get("tp_percent",0.8))
        self.initial_order_percent.setValue(g.get("base_order_percent",1.0))
        self.close_threshold_percent.setValue(g.get("saldo_threshold_percent",30.0))
        self.partial_close_percent.setValue(g.get("partial_close_percent",50.0))
        self.commission_percent.setValue( g.get("commission_percent",0.04) )
        self.slippage_percent.setValue(  g.get("slippage_percent",0.05) )
        self.lot_multiplier.setValue(    g.get("lot_multiplier",1.0) )
        self.avg_mode.setCurrentText(    g.get("avg_mode","martingale") )
        self.max_orders.setValue(       g.get("max_orders",10) )
        self.log_time_format.setText(cfg.get("log_time_format","%d/%m/%Y %H:%M:%S.%f"))
        self.ping_display.setChecked(cfg.get("ping_display",False))
        self.slippage_display.setChecked(cfg.get("slippage_display",False))

        r = cfg.get("rsi", {})
        self.rsi_period.setValue(r.get("period",14))
        self.rsi_upper.setValue(r.get("upper",70))
        self.rsi_lower.setValue(r.get("lower",30))
        self.rsi_threshold.setValue(r.get("threshold",30))

        m = cfg.get("mrc", {})
        self.mrc_entry_level.setCurrentText(m.get("entry_level","3"))
        self.mrc_exit_level .setCurrentText(m.get("exit_level","1"))
        self.mrc_entry_candle_type.setCurrentText(m.get("entry_candle_type","cross"))
        self.mrc_exit_candle_type .setCurrentText(m.get("exit_candle_type","reverse"))

        z = cfg.get("zone", {})
        # режим и уровень
        self.zone_mode.setCurrentText(str(z.get("mode",1)))
        self.zone_level.setCurrentText(str(z.get("level", "2")))
        # для symmetric (режим 2) — выделяем сразу несколько зон
        sel = set(z.get("entry_zones", []))
        for i in range(self.zone_entry_zones.count()):
            it = self.zone_entry_zones.item(i)
            it.setSelected(it.text() in sel)
        self.zone_candle_type.setCurrentText(z.get("entry_candle_type","cross"))

    def save_settings(self):
        cfg = {}
        if os.path.exists(self.settings_file):
            with open(self.settings_file,'r') as f:
                cfg = yaml.safe_load(f) or {}

        cfg["mode"]            = self.mode.currentText()
        cfg["trade_direction"] = self.trade_direction.currentText()
        cfg["log_time_format"] = self.log_time_format.text()
        cfg["ping_display"]    = self.ping_display.isChecked()
        cfg["slippage_display"]= self.slippage_display.isChecked()
        cfg["global"] = {
            "leverage":               self.leverage.value(),
            "step_percent":           self.entry_step_percent.value(),
            "step_multiplier":        self.step_multiplier.value(),
            "min_step_percent":       self.min_step_percent.value(),
            "tp_percent":             self.tp_percent.value(),
            "base_order_percent":     self.initial_order_percent.value(),
            "saldo_threshold_percent":self.close_threshold_percent.value(),
            "partial_close_percent":  self.partial_close_percent.value(),
            "commission_percent":     self.commission_percent.value(),
            "slippage_percent":       self.slippage_percent.value(),
            "lot_multiplier":         self.lot_multiplier.value(),
            "avg_mode":               self.avg_mode.currentText(),
            "max_orders":             self.max_orders.value(),
        }

        cfg["rsi"] = {
            "period":    self.rsi_period.value(),
            "upper":     self.rsi_upper.value(),
            "lower":     self.rsi_lower.value(),
            "threshold": self.rsi_threshold.value(),
        }
        cfg["mrc"] = {
            "entry_level":       self.mrc_entry_level.currentText(),
            "exit_level":        self.mrc_exit_level.currentText(),
            "entry_candle_type": self.mrc_entry_candle_type.currentText(),
            "exit_candle_type":  self.mrc_exit_candle_type.currentText(),
        }
        sel = [self.zone_entry_zones.item(i).text()
               for i in range(self.zone_entry_zones.count())
               if self.zone_entry_zones.item(i).isSelected()]
        cfg["zone"] = {
            "mode":               int(self.zone_mode.currentText()),
            "level":              self.zone_level.currentText(),
            "entry_zones":        sel,
            "entry_candle_type":  self.zone_candle_type.currentText(),
        }

        with open(self.settings_file,'w') as f:
            yaml.dump(cfg, f, sort_keys=False)

        self.append_log("💾 Настройки сохранены")

    def build_settings(self):
        cfg = {
            "mode":            self.mode.currentText(),
            "trade_direction": self.trade_direction.currentText(),
            "log_time_format": self.log_time_format.text(),
            "ping_display":    self.ping_display.isChecked(),
            "slippage_display":self.slippage_display.isChecked(),
            "global": {
                "leverage":               self.leverage.value(),
                "step_percent":           self.entry_step_percent.value(),
                "step_multiplier":        self.step_multiplier.value(),
                "min_step_percent":       self.min_step_percent.value(),
                "tp_percent":             self.tp_percent.value(),
                "base_order_percent":     self.initial_order_percent.value(),
                "saldo_threshold_percent":self.close_threshold_percent.value(),
                "partial_close_percent":  self.partial_close_percent.value(),
                "commission_percent":     self.commission_percent.value(),
                "slippage_percent":       self.slippage_percent.value(),
                "lot_multiplier":         self.lot_multiplier.value(),
                "avg_mode":               self.avg_mode.currentText(),
                "max_orders":             self.max_orders.value(),
            },
            "rsi": {
                "period":    self.rsi_period.value(),
                "upper":     self.rsi_upper.value(),
                "lower":     self.rsi_lower.value(),
                "threshold": self.rsi_threshold.value(),
            },
            "mrc": {
                "entry_level":       self.mrc_entry_level.currentText(),
                "exit_level":        self.mrc_exit_level.currentText(),
                "entry_candle_type": self.mrc_entry_candle_type.currentText(),
                "exit_candle_type":  self.mrc_exit_candle_type.currentText(),
            },
            "zone": {
                "mode":              int(self.zone_mode.currentText()),
                "level":             self.zone_level.currentText(),
                "entry_zones":       [ self.zone_entry_zones.item(i).text()
                                       for i in range(self.zone_entry_zones.count())
                                       if self.zone_entry_zones.item(i).isSelected() ],
                "entry_candle_type": self.zone_candle_type.currentText(),
            },
            "dry_run": self.ping_display.isChecked()
        }
        return cfg

if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = SettingsWindow()
    win.resize(1200, 700)
    win.show()
    sys.exit(app.exec())