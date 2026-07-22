"""Stateful Daily Factory Data Simulator.

Evolves the previous day's factory state by applying realistic operational
events, then writes a new dated CSV snapshot plus a structured change log.
Emits the canonical schema so a future ERP/MES adapter is a drop-in
replacement. Entry points: :class:`simulator.engine.SimulatorEngine` and the
``simulator.run_simulator`` CLI.
"""
