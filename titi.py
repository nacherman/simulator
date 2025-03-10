import os
import tkinter as tk
from tkinter import messagebox, Toplevel
import copy
import numpy as np
from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import *
import datetime
from tkinter import simpledialog, ttk, scrolledtext
from collections import defaultdict
import subprocess
import re

# Konfiguration
ngspice_executable_path = r"C:\Users\nilsa\Downloads\ngspice-44.2_64\Spice64\bin\ngspice.exe"
os.environ['NGSPICE_EXECUTABLE'] = ngspice_executable_path

def log_message(message, log_file="simulation_log.txt"):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")
    print(f"[{timestamp}] {message}")

if not os.path.exists(ngspice_executable_path):
    messagebox.showerror("NGSPICE Fehler", f"NGSpice ausführbare Datei nicht gefunden unter: {ngspice_executable_path}.")
    log_message(f"Fehler: NGSpice nicht gefunden unter {ngspice_executable_path}")

class Component:
    def __init__(self, canvas, x, y):
        self.canvas = canvas
        self.x = x
        self.y = y
        self.id = None
        self.terminals = []
        self.items = []
        self.create()

    def __deepcopy__(self, memo):
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        for k, v in self.__dict__.items():
            if k == "canvas":
                result.__dict__[k] = v
            else:
                result.__dict__[k] = copy.deepcopy(v, memo)
        return result

    def create(self):
        raise NotImplementedError("Muss von Unterklasse implementiert werden")

    def move(self, dx, dy):
        self.x += dx
        self.y += dy
        if self.id:
            self.canvas.move(self.id, dx, dy)
        for t in self.terminals:
            self.canvas.move(t, dx, dy)

    def draw_copy(self, canvas):
        raise NotImplementedError("Muss von Unterklasse implementiert werden")

    def get_all_items(self):
        return self.items

    def get_state(self):
        return {
            "type": self.__class__.__name__,
            "x": self.x,
            "y": self.y,
            "value": getattr(self, 'value', None),
            "name": getattr(self, 'name', None),
            "rotation": getattr(self, 'rotation', 0),
            "source_type": getattr(self, 'source_type', None),
            "meter_type": getattr(self, 'meter_type', None),
            "is_ohmmeter": getattr(self, 'is_ohmmeter', False)
        }

class SourceComponent(Component):
    def __init__(self, canvas, x, y, source_type="voltage", value=5.0, name="Q"):
        self.source_type = source_type
        self.value = value
        self.name = name
        self.text_id = None
        self.symbol_ids = []
        super().__init__(canvas, x, y)

    def create(self):
        width, height = 80, 40
        self.id = self.canvas.create_rectangle(self.x - width/2, self.y - height/2,
                                               self.x + width/2, self.y + height/2,
                                               fill="#D3D3D3", tags=("source", "component"))
        self.items.append(self.id)
        label = f"{self.name}\n{self.value:.2f} {'V' if self.source_type == 'voltage' else 'A'}"
        self.text_id = self.canvas.create_text(self.x, self.y - (height/4 if self.source_type == "voltage" else 0),
                                               text=label, font=("Arial", 10),
                                               tags=("source", "component", "editable"))
        self.items.append(self.text_id)
        left_t = self.canvas.create_oval(self.x - width/2 - 5, self.y - 5,
                                         self.x - width/2 + 5, self.y + 5,
                                         fill="red", tags="terminal", activefill="green")
        right_t = self.canvas.create_oval(self.x + width/2 - 5, self.y - 5,
                                          self.x + width/2 + 5, self.y + 5,
                                          fill="red", tags="terminal", activefill="green")
        self.terminals = [left_t, right_t]
        self.items.extend(self.terminals)
        if self.source_type == "voltage":
            plus_id = self.canvas.create_text(self.x - width/4, self.y,
                                             text="+", font=("Arial", 14, "bold"), fill="blue",
                                             tags=("symbol", "editable"))
            minus_id = self.canvas.create_text(self.x + width/4, self.y,
                                               text="–", font=("Arial", 14, "bold"), fill="blue",
                                               tags=("symbol", "editable"))
            self.symbol_ids = [plus_id, minus_id]
            self.items.extend(self.symbol_ids)

    def move(self, dx, dy):
        super().move(dx, dy)
        if self.text_id:
            self.canvas.move(self.text_id, dx, dy)
        for s in self.symbol_ids:
            self.canvas.move(s, dx, dy)

    def rotate(self):
        for obj in self.items:
            self.canvas.delete(obj)
        self.x, self.y = self.y, self.x
        self.create()

    def draw_copy(self, canvas):
        width, height = 80, 40
        rect = canvas.create_rectangle(self.x - width/2, self.y - height/2,
                                       self.x + width/2, self.y + height/2,
                                       fill="#D3D3D3")
        label = f"{self.name}\n{self.value:.2f} {'V' if self.source_type == 'voltage' else 'A'}"
        txt = canvas.create_text(self.x, self.y - (height/4 if self.source_type == "voltage" else 0),
                                 text=label, font=("Arial", 10))
        left = canvas.create_oval(self.x - width/2 - 5, self.y - 5,
                                  self.x - width/2 + 5, self.y + 5,
                                  fill="red")
        right = canvas.create_oval(self.x + width/2 - 5, self.y - 5,
                                   self.x + width/2 + 5, self.y + 5,
                                   fill="red")
        return (rect, txt, left, right)

class CircuitComponent(Component):
    def __init__(self, canvas, x, y, is_ohmmeter=False, name="R"):
        self.is_ohmmeter = is_ohmmeter
        self.name = name
        self.value = 100.0 if not is_ohmmeter else None
        self.rotation = 0
        self.text_id = None
        self.highlight_id = None
        super().__init__(canvas, x, y)

    def create(self):
        if self.rotation in [0, 180]:
            width, height = 80, 40
            label_x = self.x
            label_y = self.y + height/2 + 12
        else:
            width, height = 40, 80
            label_x = self.x + width/2 + 12
            label_y = self.y
        if self.is_ohmmeter:
            self.id = self.canvas.create_rectangle(self.x - width/2, self.y - height/2,
                                                  self.x + width/2, self.y + height/2,
                                                  fill="#808080", tags=("component", "ohmmeter"))
            self.text_id = self.canvas.create_text(self.x, self.y, text=f"{self.name}\n0.00Ω",
                                                  font=("Arial", 12),
                                                  tags=("component", "ohmmeter", "editable"))
        else:
            self.id = self.canvas.create_oval(self.x - width/2, self.y - height/2,
                                             self.x + width/2, self.y + height/2,
                                             fill="lightblue", tags=("component", "resistor"))
            label = f"{self.name}\n{self.value:.2f}Ω"
            self.text_id = self.canvas.create_text(label_x, label_y, text=label,
                                                  font=("Arial", 10),
                                                  tags=("label", "editable"))
        self.items = [self.id, self.text_id]
        self.create_terminals(width, height)

    def create_terminals(self, width, height):
        self.terminals = []
        if self.rotation in [0, 180]:
            left_t = self.canvas.create_oval(self.x - width/2 - 5, self.y - 5,
                                            self.x - width/2 + 5, self.y + 5,
                                            fill="red", tags="terminal", activefill="green")
            right_t = self.canvas.create_oval(self.x + width/2 - 5, self.y - 5,
                                             self.x + width/2 + 5, self.y + 5,
                                             fill="red", tags="terminal", activefill="green")
            self.terminals.extend([left_t, right_t])
        else:
            top_t = self.canvas.create_oval(self.x - 5, self.y - height/2 - 5,
                                           self.x + 5, self.y - height/2 + 5,
                                           fill="red", tags="terminal", activefill="green")
            bot_t = self.canvas.create_oval(self.x - 5, self.y + height/2 - 5,
                                           self.x + 5, self.y + height/2 + 5,
                                           fill="red", tags="terminal", activefill="green")
            self.terminals.extend([top_t, bot_t])
        self.items.extend(self.terminals)

    def move(self, dx, dy):
        super().move(dx, dy)
        if self.text_id:
            self.canvas.move(self.text_id, dx, dy)
        if self.highlight_id:
            self.canvas.move(self.highlight_id, dx, dy)

    def rotate(self):
        for obj in self.items:
            self.canvas.delete(obj)
        if self.highlight_id:
            self.canvas.delete(self.highlight_id)
            self.highlight_id = None
        self.rotation = (self.rotation + 90) % 360
        self.create()

    def highlight(self, color="#FF0000"):
        coords = self.canvas.coords(self.id)
        if not coords:
            return
        if self.is_ohmmeter:
            self.highlight_id = self.canvas.create_rectangle(*coords, outline=color, width=3, tags="highlight")
        else:
            self.highlight_id = self.canvas.create_oval(*coords, outline=color, width=3, tags="highlight")
        self.canvas.tag_lower(self.highlight_id, self.id)

    def unhighlight(self):
        if self.highlight_id:
            self.canvas.delete(self.highlight_id)
            self.highlight_id = None

    def draw_copy(self, canvas):
        if self.rotation in [0, 180]:
            width, height = 80, 40
            label_x = self.x
            label_y = self.y + height/2 + 12
        else:
            width, height = 40, 80
            label_x = self.x + width/2 + 12
            label_y = self.y
        if self.is_ohmmeter:
            rect = canvas.create_rectangle(self.x - width/2, self.y - height/2,
                                          self.x + width/2, self.y + height/2,
                                          fill="#808080")
            txt = canvas.create_text(self.x, self.y, text=f"{self.name}\n0.00Ω", font=("Arial", 12))
        else:
            rect = canvas.create_oval(self.x - width/2, self.y - height/2,
                                     self.x + width/2, self.y + height/2,
                                     fill="lightblue")
            txt = canvas.create_text(label_x, label_y,
                                    text=f"{self.name}\n{self.value:.2f}Ω",
                                    font=("Arial", 10))
        left = canvas.create_oval(self.x - width/2 - 5, self.y - 5,
                                 self.x - width/2 + 5, self.y + 5,
                                 fill="red")
        right = canvas.create_oval(self.x + width/2 - 5, self.y - 5,
                                  self.x + width/2 + 5, self.y + 5,
                                  fill="red")
        return (rect, txt, left, right)

class GroundComponent(Component):
    def __init__(self, canvas, x, y):
        self.line_ids = []
        super().__init__(canvas, x, y)

    def create(self):
        line1 = self.canvas.create_line(self.x - 20, self.y, self.x + 20, self.y, width=2, fill="black", tags=("ground", "component"))
        self.line_ids.append(line1)
        self.id = line1
        self.terminal = self.canvas.create_oval(self.x - 5, self.y - 5, self.x + 5, self.y + 5,
                                               fill="green", tags="terminal", activefill="yellow")
        self.terminals = [self.terminal]
        line2 = self.canvas.create_line(self.x, self.y, self.x, self.y + 20, width=2, fill="black", tags=("ground", "component"))
        line3 = self.canvas.create_line(self.x - 10, self.y + 10, self.x + 10, self.y + 10, width=2, fill="black", tags=("ground", "component"))
        self.line_ids.extend([line2, line3])
        self.items = [line1, line2, line3, self.terminal]

    def move(self, dx, dy):
        super().move(dx, dy)
        for line_id in self.line_ids:
            self.canvas.move(line_id, dx, dy)

    def draw_copy(self, canvas):
        canvas.create_line(self.x - 20, self.y, self.x + 20, self.y, width=2, fill="black")
        canvas.create_oval(self.x - 5, self.y - 5, self.x + 5, self.y + 5, fill="green")
        canvas.create_line(self.x, self.y, self.x, self.y + 20, width=2, fill="black")
        canvas.create_line(self.x - 10, self.y + 10, self.x + 10, self.y + 10, width=2, fill="black")

class MeterComponent(Component):
    def __init__(self, canvas, simulator, x, y, meter_type="general", name=None):
        self.canvas = canvas
        self.simulator = simulator
        self.meter_type = meter_type
        self.name = name if name else f"{'V' if meter_type == 'voltmeter' else 'A' if meter_type == 'ammeter' else 'M'}{len(simulator.meters)+1}"
        self.text_id = None
        super().__init__(canvas, x, y)

    def create(self):
        width, height = 80, 40
        self.id = self.canvas.create_rectangle(self.x - width/2, self.y - height/2,
                                              self.x + width/2, self.y + height/2,
                                              fill="#ADD8E6", tags=("component", "meter"))
        if self.meter_type == "voltmeter":
            label = f"{self.name}\n0.00 V"
        elif self.meter_type == "ammeter":
            label = f"{self.name}\n0.00 mA"
        else:
            label = f"{self.name}\nMeter"
        self.text_id = self.canvas.create_text(self.x, self.y, text=label,
                                              font=("Arial", 12),
                                              tags=("component", "meter", "editable"))
        left_t = self.canvas.create_oval(self.x - width/2 - 5, self.y - 5,
                                        self.x - width/2 + 5, self.y + 5,
                                        fill="red", tags="terminal", activefill="green")
        right_t = self.canvas.create_oval(self.x + width/2 - 5, self.y - 5,
                                         self.x + width/2 + 5, self.y + 5,
                                         fill="red", tags="terminal", activefill="green")
        self.terminals = [left_t, right_t]
        self.items = [self.id, self.text_id, left_t, right_t]

    def move(self, dx, dy):
        super().move(dx, dy)
        if self.text_id:
            self.canvas.move(self.text_id, dx, dy)

    def draw_copy(self, canvas):
        width, height = 80, 40
        rect = canvas.create_rectangle(self.x - width/2, self.y - height/2,
                                      self.x + width/2, self.y + height/2,
                                      fill="#ADD8E6")
        if self.meter_type == "voltmeter":
            label = f"{self.name}\n0.00 V"
        elif self.meter_type == "ammeter":
            label = f"{self.name}\n0.00 mA"
        else:
            label = f"{self.name}\nMeter"
        txt = canvas.create_text(self.x, self.y, text=label, font=("Arial", 12))
        left = canvas.create_oval(self.x - width/2 - 5, self.y - 5,
                                 self.x - width/2 + 5, self.y + 5,
                                 fill="red")
        right = canvas.create_oval(self.x + width/2 - 5, self.y - 5,
                                  self.x + width/2 + 5, self.y + 5,
                                  fill="red")
        return (rect, txt, left, right)

    def open_meter_analysis(self, simulator):
        results = simulator.simulate_with_spice()
        result = results.get(self.text_id, {})
        if self.meter_type == "voltmeter":
            v = result.get("V_th", 0)
            self.canvas.itemconfig(self.text_id, text=f"{self.name}\n{v:.2f} V")
            msg = f"Voltmeter {self.name}: {v:.2f} V"
        elif self.meter_type == "ammeter":
            i = result.get("I_n", 0)
            self.canvas.itemconfig(self.text_id, text=f"{self.name}\n{i*1000:.2f} mA")
            msg = f"Ammeter {self.name}: {i*1000:.2f} mA"
        else:
            msg = (f"Meter-Analyse {self.name}:\n"
                   f"V_th = {result.get('V_th', 0):.2f} V\n"
                   f"I_n = {result.get('I_n', 0):.2f} A\n"
                   f"R_th = {result.get('R_th', float('inf')):.2f} Ω")
        top = Toplevel(self.canvas)
        top.title(f"Meter-Analyse {self.name}")
        tk.Label(top, text=msg, font=("Arial", 12), justify="left").pack(padx=10, pady=10)

class AdvancedAnalysis:
    def __init__(self, root, simulator):
        self.simulator = simulator
        self.window = Toplevel(root)
        self.window.title("Erweiterte Analyse und Lösungsweg")
        self.copy_canvas = tk.Canvas(self.window, width=600, height=400, bg="white")
        self.copy_canvas.pack(padx=10, pady=10)
        self.text_area = scrolledtext.ScrolledText(self.window, width=80, height=15, font=("Arial", 12))
        self.text_area.pack(padx=10, pady=10)
        self.draw_circuit_copy()
        explanation = self.generate_explanation()
        self.text_area.insert(tk.END, explanation)
        self.text_area.config(state="disabled")

    def draw_circuit_copy(self):
        for comp in self.simulator.components:
            comp.draw_copy(self.copy_canvas)
        for ohm in self.simulator.ohmmeters:
            ohm.draw_copy(self.copy_canvas)
        for src in self.simulator.sources:
            src.draw_copy(self.copy_canvas)
        for m in self.simulator.meters:
            m.draw_copy(self.copy_canvas)
        for g in self.simulator.grounds:
            g.draw_copy(self.copy_canvas)
        for wire in self.simulator.wires:
            start_coords = self.simulator.get_terminal_coords(wire["start"])
            end_coords = self.simulator.get_terminal_coords(wire["end"])
            self.copy_canvas.create_line(*start_coords, *end_coords, width=2)

    def describe_circuit(self):
        desc = "Schaltung enthält:\n"
        node_map = self.simulator.generate_node_map()
        for comp in self.simulator.components:
            if not comp.is_ohmmeter:
                n1 = node_map[comp.terminals[0]]
                n2 = node_map[comp.terminals[1]]
                desc += f"- Widerstand {comp.name}: {comp.value}Ω zwischen Knoten {n1} und {n2}\n"
        for src in self.simulator.sources:
            n1 = node_map[src.terminals[0]]
            n2 = node_map[src.terminals[1]]
            desc += f"- {src.source_type.capitalize()}quelle {src.name}: {src.value}{'V' if src.source_type == 'voltage' else 'A'} zwischen Knoten {n1} und {n2}\n"
        for ohm in self.simulator.ohmmeters:
            n1 = node_map[ohm.terminals[0]]
            n2 = node_map[ohm.terminals[1]]
            desc += f"- Ohmmeter {ohm.name} misst zwischen Knoten {n1} und {n2}\n"
        for meter in self.simulator.meters:
            n1 = node_map[meter.terminals[0]]
            n2 = node_map[meter.terminals[1]]
            desc += f"- {meter.meter_type.capitalize()} {meter.name} zwischen Knoten {n1} und {n2}\n"
        for wire in self.simulator.wires:
            start_node = node_map[wire["start"]]
            end_node = node_map[wire["end"]]
            desc += f"- Verbindung zwischen Knoten {start_node} und {end_node}\n"
        for g in self.simulator.grounds:
            desc += f"- Masse (GND) an Knoten {node_map[g.terminal]}\n"
        return desc

    def generate_explanation(self):
        lines = ["**Manuelle Analyse:**"]
        if self.simulator.ohmmeters:
            ohm = self.simulator.ohmmeters[0]
            measured = self.simulator.calculate_resistance(ohm.terminals[0], ohm.terminals[1])
            lines.append(f"Ohmmeter-Messung: {measured:.2f} Ω\n")
        lines.append("\n**NGSpice-Simulation:**")
        results = self.simulator.simulate_with_spice()
        for ohm in self.simulator.ohmmeters:
            r = results.get(ohm.name, {}).get("R", float('inf'))
            lines.append(f"Ohmmeter {ohm.name}: {r:.2f} Ω")
        for meter in self.simulator.meters:
            res = results.get(meter.text_id, {})
            lines.append(f"{meter.meter_type.capitalize()} {meter.name}: V_th={res.get('V_th', 0):.2f} V, I_n={res.get('I_n', 0)*1000:.2f} mA")
        return "\n".join(lines)

class SourceInputDialog(simpledialog.Dialog):
    def __init__(self, parent, source_type="voltage"):
        self.source_type = source_type
        self.value = None
        self.unit = None
        super().__init__(parent, title="Quelle hinzufügen")

    def body(self, master):
        tk.Label(master, text="Wert:").grid(row=0, column=0, padx=5, pady=5)
        self.value_entry = tk.Entry(master)
        self.value_entry.grid(row=0, column=1, padx=5, pady=5)
        unit_options = ["V", "mV", "µV"] if self.source_type == "voltage" else ["A", "mA", "µA"]
        tk.Label(master, text="Einheit:").grid(row=0, column=2, padx=5, pady=5)
        self.unit_var = tk.StringVar(value=unit_options[0])
        self.unit_dropdown = ttk.Combobox(master, textvariable=self.unit_var,
                                          values=unit_options, state="readonly", width=5)
        self.unit_dropdown.grid(row=0, column=3, padx=5, pady=5)
        return self.value_entry

    def apply(self):
        try:
            self.value = float(self.value_entry.get())
            self.unit = self.unit_var.get()
        except ValueError:
            self.value = None

class EditLabelDialog(simpledialog.Dialog):
    def __init__(self, parent, current_text):
        self.new_text = current_text
        super().__init__(parent, title="Label bearbeiten")

    def body(self, master):
        tk.Label(master, text="Neuer Labeltext:").grid(row=0, column=0, padx=5, pady=5)
        self.entry = tk.Entry(master)
        self.entry.insert(0, self.new_text)
        self.entry.grid(row=0, column=1, padx=5, pady=5)
        return self.entry

    def apply(self):
        self.new_text = self.entry.get()

class ResistorSimulator:
    def __init__(self, root):
        self.root = root
        self.root.title("Circuit Simulator Pro+")
        self.zoom_factor = 1.0
        self.undo_stack = []
        self.redo_stack = []
        self.canvas_frame = tk.Frame(root)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)
        self.hbar = tk.Scrollbar(self.canvas_frame, orient=tk.HORIZONTAL)
        self.hbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.vbar = tk.Scrollbar(self.canvas_frame, orient=tk.VERTICAL)
        self.vbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas = tk.Canvas(self.canvas_frame, width=1000, height=700, bg="white",
                                xscrollcommand=self.hbar.set, yscrollcommand=self.vbar.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.hbar.config(command=self.canvas.xview)
        self.vbar.config(command=self.canvas.yview)
        self.components = []
        self.ohmmeters = []
        self.sources = []
        self.meters = []
        self.grounds = []
        self.wires = []
        self.selected_terminal = None
        self.selected_component = None
        self.dragging_component = None
        self.drag_start = (0, 0)
        self.setup_controls()
        self.setup_bindings()

    def setup_controls(self):
        frame = tk.Frame(self.root)
        frame.pack(fill=tk.X)
        tk.Button(frame, text="Add Resistor", command=lambda: self.add_component(False)).pack(side=tk.LEFT, padx=5)
        tk.Button(frame, text="Add Ohmmeter", command=lambda: self.add_component(True)).pack(side=tk.LEFT, padx=5)
        tk.Button(frame, text="Add Spannungsquelle", command=lambda: self.add_source("voltage")).pack(side=tk.LEFT, padx=5)
        tk.Button(frame, text="Add Stromquelle", command=lambda: self.add_source("current")).pack(side=tk.LEFT, padx=5)
        tk.Button(frame, text="Add Meter", command=lambda: self.add_meter("general")).pack(side=tk.LEFT, padx=5)
        tk.Button(frame, text="Add Voltmeter", command=lambda: self.add_meter("voltmeter")).pack(side=tk.LEFT, padx=5)
        tk.Button(frame, text="Add Amperemeter", command=lambda: self.add_meter("ammeter")).pack(side=tk.LEFT, padx=5)
        tk.Button(frame, text="Add Ground (GND)", command=self.add_ground).pack(side=tk.LEFT, padx=5)
        tk.Button(frame, text="Simulieren", command=self.simulate_circuit).pack(side=tk.LEFT, padx=5)
        tk.Button(frame, text="Test All Functions", command=self.test_all_functions).pack(side=tk.LEFT, padx=5)
        tk.Button(frame, text="Erweiterte Analyse", command=self.open_advanced_analysis).pack(side=tk.LEFT, padx=5)
        tk.Button(frame, text="Explain", command=self.show_explanation).pack(side=tk.LEFT, padx=5)
        self.root.bind("<Control-z>", lambda e: self.undo())
        self.root.bind("<Control-y>", lambda e: self.redo())

    def setup_bindings(self):
        self.canvas.tag_bind("component", "<Button-1>", self.start_drag)
        self.canvas.tag_bind("editable", "<Double-Button-1>", self.edit_label)
        self.canvas.bind("<Button-3>", self.show_context_menu)
        self.canvas.bind("<B1-Motion>", self.handle_drag)
        self.canvas.bind("<ButtonRelease-1>", self.stop_drag)
        self.canvas.tag_bind("terminal", "<Button-1>", self.handle_terminal_click)
        self.canvas.tag_bind("meter", "<Double-Button-1>", self.handle_meter_dbl_click)
        self.canvas.tag_bind("wire", "<Button-3>", self.delete_wire_context)
        self.canvas.bind("<MouseWheel>", self.zoom)
        self.canvas.bind("<Button-4>", self.zoom)
        self.canvas.bind("<Button-5>", self.zoom)

    def handle_meter_dbl_click(self, event):
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        item = self.canvas.find_closest(x, y)[0]
        meter = next((m for m in self.meters if item in m.get_all_items()), None)
        if meter:
            meter.open_meter_analysis(self)

    def show_context_menu(self, event):
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        item = self.canvas.find_closest(x, y)[0]
        comp = self.find_component_by_item(item)
        if comp is None:
            return
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Label bearbeiten", command=lambda: self.edit_component_label(comp))
        menu.add_command(label="Rotieren", command=lambda: self.rotate_component(comp))
        menu.add_command(label="Löschen", command=lambda: self.delete_component(comp))
        menu.tk_popup(event.x_root, event.y_root)

    def delete_wire_context(self, event):
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        item = self.canvas.find_closest(x, y)[0]
        wire = next((w for w in self.wires if w["id"] == item), None)
        if wire:
            menu = tk.Menu(self.root, tearoff=0)
            menu.add_command(label="Löschen", command=lambda: self.delete_wire(wire))
            menu.tk_popup(event.x_root, event.y_root)

    def edit_label(self, event):
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        item = self.canvas.find_closest(x, y)[0]
        comp = self.find_component_by_item(item)
        if comp and hasattr(comp, 'text_id'):
            self.edit_component_label(comp)

    def edit_component_label(self, comp):
        if not hasattr(comp, 'text_id'):
            return
        current_text = self.canvas.itemcget(comp.text_id, "text")
        dlg = EditLabelDialog(self.root, current_text)
        if dlg.new_text:
            self.canvas.itemconfig(comp.text_id, text=dlg.new_text)
            if hasattr(comp, 'name'):
                comp.name = dlg.new_text.split("\n")[0]
            self.push_state()

    def rotate_component(self, comp):
        if hasattr(comp, 'rotate'):
            comp.rotate()
            self.update_wires()
            self.push_state()

    def delete_component(self, comp):
        for obj in comp.get_all_items():
            self.canvas.delete(obj)
        if isinstance(comp, CircuitComponent):
            if comp.is_ohmmeter:
                if comp in self.ohmmeters:
                    self.ohmmeters.remove(comp)
            else:
                if comp in self.components:
                    self.components.remove(comp)
        elif isinstance(comp, SourceComponent):
            if comp in self.sources:
                self.sources.remove(comp)
        elif isinstance(comp, MeterComponent):
            if comp in self.meters:
                self.meters.remove(comp)
        elif isinstance(comp, GroundComponent):
            if comp in self.grounds:
                self.grounds.remove(comp)
        wires_to_remove = [w for w in self.wires if w["start"] in comp.terminals or w["end"] in comp.terminals]
        for w in wires_to_remove:
            self.canvas.delete(w["id"])
            self.wires.remove(w)
        log_message(f"Komponente {getattr(comp, 'name', 'unbenannt')} gelöscht.")
        self.push_state()

    def delete_wire(self, wire):
        self.canvas.delete(wire["id"])
        self.wires.remove(wire)
        log_message(f"Wire zwischen Terminal {wire['start']} und {wire['end']} gelöscht.")
        self.push_state()

    def find_component_by_item(self, item):
        for comp in self.components + self.ohmmeters + self.sources + self.meters + self.grounds:
            if item in comp.get_all_items():
                return comp
        return None

    def zoom(self, event):
        factor = 1.1 if (event.num == 4 or event.delta > 0) else 0.9
        self.zoom_factor *= factor
        self.canvas.scale("all", self.canvas.canvasx(event.x), self.canvas.canvasy(event.y), factor, factor)
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def push_state(self):
        state = self.get_state()
        self.undo_stack.append(state)
        if len(self.undo_stack) > 10:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        log_message("Zustand gespeichert für Undo.")

    def undo(self):
        if not self.undo_stack:
            log_message("Undo nicht möglich: Keine früheren Zustände.")
            return
        state = self.undo_stack.pop()
        self.redo_stack.append(self.get_state())
        self.set_state(state)
        log_message("Undo ausgeführt.")

    def redo(self):
        if not self.redo_stack:
            log_message("Redo nicht möglich: Keine rückgängigen Zustände.")
            return
        state = self.redo_stack.pop()
        self.undo_stack.append(self.get_state())
        self.set_state(state)
        log_message("Redo ausgeführt.")

    def get_state(self):
        state = {
            "components": [comp.get_state() for comp in self.components],
            "ohmmeters": [ohm.get_state() for ohm in self.ohmmeters],
            "sources": [src.get_state() for src in self.sources],
            "meters": [m.get_state() for m in self.meters],
            "grounds": [g.get_state() for g in self.grounds],
            "wires": [{"start": w["start"], "end": w["end"]} for w in self.wires]
        }
        return state

    def set_state(self, state):
        self.canvas.delete("all")
        self.components = [self.create_component_from_state(s) for s in state["components"]]
        self.ohmmeters = [self.create_component_from_state(s) for s in state["ohmmeters"]]
        self.sources = [self.create_component_from_state(s) for s in state["sources"]]
        self.meters = [self.create_component_from_state(s) for s in state["meters"]]
        self.grounds = [self.create_component_from_state(s) for s in state["grounds"]]
        self.wires = []
        for wire_state in state["wires"]:
            start_terminal = wire_state["start"]
            end_terminal = wire_state["end"]
            start_coords = self.get_terminal_coords(start_terminal)
            end_coords = self.get_terminal_coords(end_terminal)
            if start_coords and end_coords:
                wire_id = self.canvas.create_line(start_coords[0], start_coords[1], end_coords[0], end_coords[1], width=2, fill="black", tags="wire")
                self.wires.append({"id": wire_id, "start": start_terminal, "end": end_terminal})

    def create_component_from_state(self, state):
        comp_type = globals()[state["type"]]
        if state["type"] == "CircuitComponent":
            comp = comp_type(self.canvas, state["x"], state["y"], is_ohmmeter=state["is_ohmmeter"], name=state["name"])
            if not state["is_ohmmeter"] and state["value"] is not None:
                comp.value = state["value"]
        elif state["type"] == "SourceComponent":
            comp = comp_type(self.canvas, state["x"], state["y"], source_type=state["source_type"], value=state["value"], name=state["name"])
        elif state["type"] == "MeterComponent":
            comp = comp_type(self.canvas, self, state["x"], state["y"], meter_type=state["meter_type"], name=state["name"])
        elif state["type"] == "GroundComponent":
            comp = comp_type(self.canvas, state["x"], state["y"])
        comp.rotation = state["rotation"]
        comp.create()
        return comp

    def add_source(self, source_type):
        dlg = SourceInputDialog(self.root, source_type)
        if dlg.value is None:
            return
        val = dlg.value
        if dlg.unit in ["mV", "mA"]:
            val /= 1000
        elif dlg.unit in ["µV", "µA"]:
            val /= 1e6
        x, y = (700, 150) if source_type == "voltage" else (700, 300)
        name = f"VQ{len(self.sources)+1}" if source_type == "voltage" else f"IQ{len(self.sources)+1}"
        src = SourceComponent(self.canvas, x, y, source_type, val, name=name)
        self.sources.append(src)
        log_message(f"{source_type.capitalize()}quelle {name} hinzugefügt.")
        self.push_state()

    def add_component(self, is_ohmmeter):
        x, y = (150, 150) if not is_ohmmeter else (700, 100)
        name = f"Ohm{len(self.ohmmeters)+1}" if is_ohmmeter else f"R{len(self.components)+1}"
        comp = CircuitComponent(self.canvas, x, y, is_ohmmeter, name=name)
        if is_ohmmeter:
            self.ohmmeters.append(comp)
        else:
            self.components.append(comp)
        log_message(f"{'Ohmmeter' if is_ohmmeter else 'Widerstand'} {name} hinzugefügt.")
        self.push_state()

    def add_meter(self, meter_type="general"):
        x, y = 700, 400 + (len(self.meters) * 100)
        m = MeterComponent(self.canvas, self, x, y, meter_type=meter_type)
        self.meters.append(m)
        log_message(f"{meter_type.capitalize()} {m.name} hinzugefügt an Position ({x}, {y}).")
        self.push_state()

    def add_ground(self):
        x, y = 700, 600
        g = GroundComponent(self.canvas, x, y)
        self.grounds.append(g)
        log_message("Ground (GND) hinzugefügt.")
        self.push_state()

    def test_all_functions(self):
        self.canvas.delete("all")
        self.components.clear()
        self.ohmmeters.clear()
        self.sources.clear()
        self.meters.clear()
        self.grounds.clear()
        self.wires.clear()

        src = SourceComponent(self.canvas, 100, 300, "voltage", 2.0, "V1")
        self.sources.append(src)

        r1 = CircuitComponent(self.canvas, 300, 300, False, "R1")
        r1.value = 100
        self.canvas.itemconfig(r1.text_id, text=f"R1\n100.00Ω")
        self.components.append(r1)

        r2 = CircuitComponent(self.canvas, 500, 300, False, "R2")
        r2.value = 100
        self.canvas.itemconfig(r2.text_id, text=f"R2\n100.00Ω")
        self.components.append(r2)

        volt = MeterComponent(self.canvas, self, 700, 200, "voltmeter", "V1")
        self.meters.append(volt)

        amp = MeterComponent(self.canvas, self, 700, 400, "ammeter", "A1")
        self.meters.append(amp)

        gnd = GroundComponent(self.canvas, 500, 500)
        self.grounds.append(gnd)

        self.create_connection(src.terminals[0], r1.terminals[0])
        self.create_connection(r1.terminals[1], r2.terminals[0])
        self.create_connection(r2.terminals[1], gnd.terminal)
        self.create_connection(r1.terminals[0], volt.terminals[0])
        self.create_connection(r1.terminals[1], volt.terminals[1])
        self.create_connection(src.terminals[0], amp.terminals[0])
        self.create_connection(r1.terminals[0], amp.terminals[1])

        self.push_state()
        self.simulate_circuit()
        log_message("Testschaltung erstellt und simuliert.")

    def handle_terminal_click(self, event):
        current_terminal = self.canvas.find_closest(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))[0]
        if self.selected_terminal is None:
            self.selected_terminal = current_terminal
            self.canvas.itemconfig(current_terminal, fill="yellow")
        else:
            if current_terminal != self.selected_terminal:
                self.create_connection(self.selected_terminal, current_terminal)
            self.reset_selection()

    def reset_selection(self):
        if self.selected_terminal:
            self.canvas.itemconfig(self.selected_terminal, fill="red")
            self.selected_terminal = None

    def create_connection(self, start_terminal, end_terminal):
        start_coords = self.get_terminal_coords(start_terminal)
        end_coords = self.get_terminal_coords(end_terminal)
        wire = self.canvas.create_line(*start_coords, *end_coords, width=2, tags="wire")
        self.wires.append({"id": wire, "start": start_terminal, "end": end_terminal})
        log_message(f"Verbindung zwischen Terminal {start_terminal} und {end_terminal} erstellt.")
        self.push_state()

    def get_terminal_coords(self, terminal_id):
        coords = self.canvas.coords(terminal_id)
        if not coords:
            return None
        return (coords[0] + 5, coords[1] + 5)

    def start_drag(self, event):
        item = self.canvas.find_closest(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))[0]
        for comp in self.components + self.ohmmeters + self.sources + self.meters + self.grounds:
            if item in comp.get_all_items():
                self.dragging_component = comp
                self.selected_component = comp
                self.drag_start = (event.x, event.y)
                break

    def handle_drag(self, event):
        if self.dragging_component:
            dx = event.x - self.drag_start[0]
            dy = event.y - self.drag_start[1]
            self.dragging_component.move(dx, dy)
            self.drag_start = (event.x, event.y)
            self.update_wires()

    def stop_drag(self, event):
        if self.dragging_component:
            self.push_state()
        self.dragging_component = None

    def update_wires(self):
        for wire in self.wires:
            start = self.get_terminal_coords(wire["start"])
            end = self.get_terminal_coords(wire["end"])
            if start and end:
                self.canvas.coords(wire["id"], *start, *end)

    def generate_spice_netlist(self, measure_mode=False, active_ohmmeter=None):
        circuit = Circuit('Schaltkreis Simulation')
        node_map = self.generate_node_map()
        if self.grounds:
            ground_node = self.grounds[0].terminal
            node_map[ground_node] = "0"
        next_node = 1
        for comp in self.components + self.sources + self.ohmmeters + self.meters + self.grounds:
            terminals = [comp.terminal] if isinstance(comp, GroundComponent) else comp.terminals
            for t in terminals:
                if t not in node_map:
                    node_map[t] = f"N{next_node}"
                    next_node += 1

        for comp in self.components:
            if not comp.is_ohmmeter:
                n1 = node_map[comp.terminals[0]]
                n2 = node_map[comp.terminals[1]]
                circuit.R(comp.name, n1, n2, comp.value @ u_Ω)

        for src in self.sources:
            n1 = node_map[src.terminals[0]]
            n2 = node_map[src.terminals[1]]
            if measure_mode:
                circuit.V(src.name, n1, n2, 0 @ u_V) if src.source_type == "voltage" else circuit.I(src.name, n1, n2, 0 @ u_A)
            else:
                circuit.V(src.name, n1, n2, src.value @ u_V) if src.source_type == "voltage" else circuit.I(src.name, n1, n2, src.value @ u_A)

        for ohm in self.ohmmeters:
            n1 = node_map[ohm.terminals[0]]
            n2 = node_map[ohm.terminals[1]]
            if measure_mode and ohm == active_ohmmeter:
                circuit.V(f"{ohm.name}_test", n1, n2, 1 @ u_V)
            else:
                circuit.R(f"{ohm.name}_probe", n1, n2, 1e6 @ u_Ω)

        for meter in self.meters:
            n1 = node_map[meter.terminals[0]]
            n2 = node_map[meter.terminals[1]]
            if meter.meter_type == "ammeter":
                circuit.R(f"{meter.name}_probe", n1, n2, 1e-6 @ u_Ω)  # Kleiner Widerstand für Strommessung
            elif meter.meter_type == "voltmeter":
                circuit.R(f"{meter.name}_probe", n1, n2, 1e6 @ u_Ω)  # Großer Widerstand für Spannungsmessung

        log_message(f"Generated SPICE netlist:\n{str(circuit)}")
        log_message(f"Node map: {node_map}")
        return circuit, node_map

    def generate_node_map(self):
        node_map = {}
        all_terminals = set()
        for comp in self.components + self.sources + self.ohmmeters + self.meters + self.grounds:
            terminals = [comp.terminal] if isinstance(comp, GroundComponent) else comp.terminals
            all_terminals.update(terminals)
        for wire in self.wires:
            all_terminals.discard(wire["start"])
            all_terminals.discard(wire["end"])
            start_group = self.get_connected_terminals(wire["start"])
            end_group = self.get_connected_terminals(wire["end"])
            all_terminals.update(start_group)
            all_terminals.update(end_group)
        for terminal in all_terminals:
            if terminal not in node_map:
                connected = self.get_connected_terminals(terminal)
                node_name = f"N{len(node_map) + 1}"
                for t in connected:
                    node_map[t] = node_name
        return node_map

    def get_connected_terminals(self, terminal):
        connected = {terminal}
        stack = [terminal]
        while stack:
            current = stack.pop()
            for wire in self.wires:
                if wire["start"] == current and wire["end"] not in connected:
                    connected.add(wire["end"])
                    stack.append(wire["end"])
                elif wire["end"] == current and wire["start"] not in connected:
                    connected.add(wire["start"])
                    stack.append(wire["start"])
        return connected

    def simulate_with_spice(self):
        if not os.path.exists(ngspice_executable_path):
            messagebox.showerror("SPICE Fehler", f"NGSpice nicht gefunden unter: {ngspice_executable_path}")
            log_message(f"Fehler: NGSpice nicht gefunden unter {ngspice_executable_path}")
            return {}
        if not self.components and not self.ohmmeters and not self.meters:
            messagebox.showerror("SPICE Fehler", "Keine Komponenten zum Simulieren vorhanden.")
            log_message("Fehler: Keine Komponenten zum Simulieren vorhanden.")
            return {}
        if not self.grounds:
            messagebox.showerror("SPICE Fehler", "Bitte füge ein GND (Masse) hinzu.")
            log_message("Fehler: Keine Masse (GND) vorhanden.")
            return {}

        results = {}
        output_file = "simulation_results.txt"

        # Ohmmeter-Simulation
        if self.ohmmeters:
            for ohm in self.ohmmeters:
                circuit, node_map = self.generate_spice_netlist(measure_mode=True, active_ohmmeter=ohm)
                netlist_file = f"temp_ohm_{ohm.name}.cir"
                with open(netlist_file, "w", encoding="utf-8") as f:
                    f.write(str(circuit))
                    all_nodes = set(node_map.values()) - {"0"}
                    nodes_str = " ".join([f"v({node})" for node in all_nodes])
                    f.write(f"\n.op\n.control\nset noaskquit\nop\nprint {nodes_str} > {output_file}\nedisplay\n.endc\n.end\n")
                try:
                    log_message(f"Simuliere Ohmmeter {ohm.name} mit Netzliste {netlist_file}")
                    process = subprocess.run([ngspice_executable_path, "-b", netlist_file], check=True, text=True, capture_output=True, timeout=30)
                    log_message(f"NGSpice stdout:\n{process.stdout}")
                    log_message(f"NGSpice stderr:\n{process.stderr}")
                    if os.path.exists(output_file):
                        with open(output_file, "r", encoding="utf-8") as f:
                            content = f.read()
                            log_message(f"Inhalt von {output_file} für Ohmmeter {ohm.name}:\n{content}")
                            voltages = {}
                            for line in content.splitlines():
                                if "=" in line:
                                    key, value = line.split("=")
                                    key = key.strip()
                                    value = float(value.strip())
                                    voltages[key] = value
                            n1, n2 = node_map[ohm.terminals[0]], node_map[ohm.terminals[1]]
                            v1 = voltages.get(f"v({n1})", 0.0)
                            v2 = voltages.get(f"v({n2})", 0.0)
                            v_diff = abs(v1 - v2)
                            i_test = 1.0 / 1e6  # Strom durch Testspannung bei 1MΩ
                            r_measured = v_diff / i_test if i_test > 0 else float('inf')
                            results[ohm.name] = {"R": r_measured}
                            self.canvas.itemconfig(ohm.text_id, text=f"{ohm.name}\n{r_measured:.2f}Ω" if r_measured != float('inf') else f"{ohm.name}\n∞ Ω")
                            log_message(f"Ohmmeter {ohm.name} gemessener Widerstand: {r_measured:.2f}Ω")
                    else:
                        log_message(f"Ausgabedatei {output_file} nicht gefunden für Ohmmeter {ohm.name}")
                except subprocess.CalledProcessError as e:
                    log_message(f"Fehler bei Ohmmeter-Simulation {ohm.name}: {e.stderr}")
                    messagebox.showerror("Simulationsfehler", f"Ohmmeter {ohm.name} Simulation fehlgeschlagen:\n{e.stderr}")
                finally:
                    for fname in [netlist_file, output_file]:
                        if os.path.exists(fname):
                            os.remove(fname)

        # Messgeräte-Simulation
        if self.meters and self.sources:
            circuit, node_map = self.generate_spice_netlist(measure_mode=False)
            netlist_file = "temp_simulation.cir"
            with open(netlist_file, "w", encoding="utf-8") as f:
                all_nodes = set(node_map.values()) - {"0"}
                nodes_str = " ".join([f"v({node})" for node in all_nodes])
                # Ströme durch Messwiderstände hinzufügen
                currents_str = " ".join([f"V{meter.name}_probe#branch" for meter in self.meters if meter.meter_type == "ammeter"])
                print_str = f"{nodes_str} {currents_str}".strip()
                f.write(str(circuit))
                f.write(f"\n.op\n.control\nset noaskquit\nop\nprint {print_str} > {output_file}\nedisplay\n.endc\n.end\n")
            try:
                log_message(f"Simuliere Messgeräte mit Netzliste {netlist_file}")
                process = subprocess.run([ngspice_executable_path, "-b", netlist_file], check=True, text=True, capture_output=True, timeout=30)
                log_message(f"NGSpice stdout:\n{process.stdout}")
                log_message(f"NGSpice stderr:\n{process.stderr}")
                if os.path.exists(output_file):
                    with open(output_file, "r", encoding="utf-8") as f:
                        content = f.read()
                        log_message(f"Inhalt von {output_file} für Messgeräte:\n{content}")
                        values = {}
                        for line in content.splitlines():
                            if "=" in line:
                                key, value = line.split("=")
                                key = key.strip()
                                value = float(value.strip())
                                values[key] = value
                        for meter in self.meters:
                            n1 = node_map[meter.terminals[0]]
                            n2 = node_map[meter.terminals[1]]
                            v1 = values.get(f"v({n1})", 0.0)
                            v2 = values.get(f"v({n2})", 0.0)
                            v_th = abs(v1 - v2)
                            if meter.meter_type == "voltmeter":
                                self.canvas.itemconfig(meter.text_id, text=f"{meter.name}\n{v_th:.2f} V")
                                i_n = v_th / 1e6  # Strom durch 1MΩ
                                log_message(f"Voltmeter {meter.name}: V_th={v_th:.2f} V")
                            elif meter.meter_type == "ammeter":
                                i_n = values.get(f"V{meter.name}_probe#branch", 0.0)  # Direkt den Strom aus NGSpice
                                self.canvas.itemconfig(meter.text_id, text=f"{meter.name}\n{i_n*1000:.2f} mA")
                                log_message(f"Ammeter {meter.name}: I_n={i_n:.6e} A")
                            else:
                                i_n = 0
                                log_message(f"Meter {meter.name}: V_th={v_th:.2f} V (general meter)")
                            results[meter.text_id] = {"V_th": v_th, "I_n": i_n}
                else:
                    log_message(f"Ausgabedatei {output_file} nicht gefunden für Messgeräte")
            except subprocess.CalledProcessError as e:
                log_message(f"Fehler bei Messgeräte-Simulation: {e.stderr}")
                messagebox.showerror("Simulationsfehler", f"Messgeräte-Simulation fehlgeschlagen:\n{e.stderr}")
            finally:
                for fname in [netlist_file, output_file]:
                    if os.path.exists(fname):
                        os.remove(fname)

        return results

    def calculate_resistance(self, term1, term2):
        node_map = self.generate_node_map()
        if term1 not in node_map or term2 not in node_map or node_map[term1] == node_map[term2]:
            return float('inf')
        resistances = {}
        for comp in self.components:
            if not comp.is_ohmmeter:
                n1 = node_map[comp.terminals[0]]
                n2 = node_map[comp.terminals[1]]
                resistances[(n1, n2)] = comp.value
                resistances[(n2, n1)] = comp.value
        start_node = node_map[term1]
        end_node = node_map[term2]

        def find_parallel_resistance(graph, start, end):
            visited = set()
            paths = []
            def dfs(current, target, path_resistances):
                if current == target:
                    paths.append(path_resistances[:])
                    return
                visited.add(current)
                for (n1, n2), r in graph.items():
                    if n1 == current and n2 not in visited:
                        path_resistances.append(r)
                        dfs(n2, target, path_resistances)
                        path_resistances.pop()
                    elif n2 == current and n1 not in visited:
                        path_resistances.append(r)
                        dfs(n1, target, path_resistances)
                        path_resistances.pop()
                visited.remove(current)
            dfs(start, end, [])
            if not paths:
                return float('inf')
            total_conductance = 0
            for path in paths:
                path_resistance = sum(path)
                if path_resistance > 0:
                    total_conductance += 1 / path_resistance
            return 1 / total_conductance if total_conductance > 0 else float('inf')

        return find_parallel_resistance(resistances, start_node, end_node)

    def simulate_circuit(self):
        results = self.simulate_with_spice()
        if results:
            messagebox.showinfo("Simulation", "Simulation abgeschlossen. Ergebnisse wurden aktualisiert.")
            log_message("Simulation erfolgreich abgeschlossen.")
        else:
            log_message("Simulation fehlgeschlagen oder keine Ergebnisse.")

    def open_advanced_analysis(self):
        if not self.components and not self.ohmmeters and not self.meters:
            messagebox.showerror("Analyse Fehler", "Keine Komponenten zum Analysieren vorhanden.")
            return
        AdvancedAnalysis(self.root, self)

    def show_explanation(self):
        if not self.components and not self.ohmmeters and not self.meters:
            messagebox.showerror("Analyse Fehler", "Keine Komponenten zum Analysieren vorhanden.")
            return
        explanation = AdvancedAnalysis(self.root, self)
        explanation.window.title("Schaltungserklärung")

if __name__ == "__main__":
    root = tk.Tk()
    app = ResistorSimulator(root)
    root.mainloop()