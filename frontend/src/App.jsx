import React, { useState, useEffect, useRef } from 'react';
import { 
  ShieldAlert, 
  ShieldCheck, 
  Lock, 
  Unlock, 
  Radio, 
  HardHat, 
  AlertTriangle, 
  Activity, 
  Camera, 
  Clock, 
  MapPin, 
  RefreshCw,
  Server,
  Layers,
  Volume2
} from 'lucide-react';

import LiveCameraStream from './components/LiveCameraStream.jsx';

const API_BASE = "http://127.0.0.1:8000";
const WS_BASE = "ws://127.0.0.1:8000/ws/alerts";

export default function App() {
  const [wsConnected, setWsConnected] = useState(false);
  const [barrierState, setBarrierState] = useState('UNLOCKED');
  const [stats, setStats] = useState({
    total_checks: 0,
    total_incidents: 0,
    active_alert: false,
    last_incident_timestamp: null
  });
  const [incidents, setIncidents] = useState([]);
  const [selectedIncident, setSelectedIncident] = useState(null);
  const [filterZone, setFilterZone] = useState('ALL');

  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);

  // Initialize WebSocket connection
  const connectWebSocket = () => {
    try {
      const ws = new WebSocket(WS_BASE);
      wsRef.current = ws;

      ws.onopen = () => {
        setWsConnected(true);
        console.log("WebSocket connected to alert stream.");
      };

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === 'INITIAL_STATE') {
            if (payload.stats) {
              setStats(payload.stats);
              setBarrierState(payload.stats.barrier_state || 'UNLOCKED');
            }
            if (payload.recent_incidents) {
              setIncidents(payload.recent_incidents);
            }
          } else if (payload.type === 'NEW_VIOLATION_ALERT') {
            const newIncident = payload.data;
            setIncidents(prev => [newIncident, ...prev.slice(0, 49)]);
            if (payload.stats) {
              setStats(payload.stats);
              setBarrierState(payload.stats.barrier_state || 'LOCKED');
            }
          }
        } catch (err) {
          console.error("Error parsing WS message:", err);
        }
      };

      ws.onclose = () => {
        setWsConnected(false);
        reconnectTimeoutRef.current = setTimeout(connectWebSocket, 3000);
      };

      ws.onerror = (err) => {
        console.warn("WebSocket encounter error:", err);
        ws.close();
      };
    } catch (e) {
      console.warn("WebSocket initialization exception:", e);
      reconnectTimeoutRef.current = setTimeout(connectWebSocket, 3000);
    }
  };

  useEffect(() => {
    connectWebSocket();
    // Poll REST stats as backup
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/stats`);
        if (res.ok) {
          const data = await res.json();
          setStats(data);
          setBarrierState(data.barrier_state);
        }
      } catch (err) {
        // Backend offline or starting up
      }
    }, 4000);

    return () => {
      clearInterval(interval);
      if (wsRef.current) wsRef.current.close();
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
    };
  }, []);

  const isLocked = barrierState === 'LOCKED' || stats.active_alert;

  const filteredIncidents = filterZone === 'ALL' 
    ? incidents 
    : incidents.filter(i => i.zone_id === filterZone);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Top Header */}
      <header className="border-b border-slate-800 bg-slate-900/70 backdrop-blur-md sticky top-0 z-40 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="p-2.5 bg-orange-500/10 border border-orange-500/30 rounded-xl text-orange-400">
            <HardHat className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-white flex items-center space-x-2">
              <span>Autonomous PPE Access Control</span>
              <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-300 font-mono">
                EDGE v1.0
              </span>
            </h1>
            <p className="text-xs text-slate-400">Cyber-Physical Perimeter Interlock & Homography Geofencing</p>
          </div>
        </div>

        {/* Live Status Indicators */}
        <div className="flex items-center space-x-4">
          <div className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg border text-xs font-mono ${
            wsConnected 
              ? 'bg-emerald-950/40 border-emerald-500/40 text-emerald-400' 
              : 'bg-rose-950/40 border-rose-500/40 text-rose-400'
          }`}>
            <Radio className={`w-3.5 h-3.5 ${wsConnected ? 'animate-pulse' : ''}`} />
            <span>{wsConnected ? 'WS TELEMETRY LIVE' : 'WS CONNECTING...'}</span>
          </div>

          <div className="flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-slate-800/80 border border-slate-700 text-xs text-slate-300 font-mono">
            <Server className="w-3.5 h-3.5 text-blue-400" />
            <span>UART: 115200 BAUD</span>
          </div>
        </div>
      </header>

      {/* Main Content Dashboard */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 space-y-6">
        {/* Top Status Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {/* Barrier Access Status */}
          <div className={`p-5 rounded-2xl border transition-all duration-300 ${
            isLocked 
              ? 'bg-red-950/40 border-red-500/50 shadow-lg shadow-red-500/10' 
              : 'bg-emerald-950/30 border-emerald-500/40'
          }`}>
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-mono uppercase tracking-wider text-slate-400">Physical Access Barrier</span>
              {isLocked ? (
                <div className="p-2 bg-red-500/20 text-red-400 rounded-lg animate-bounce">
                  <Lock className="w-5 h-5" />
                </div>
              ) : (
                <div className="p-2 bg-emerald-500/20 text-emerald-400 rounded-lg">
                  <Unlock className="w-5 h-5" />
                </div>
              )}
            </div>
            <div className="text-2xl font-bold tracking-tight text-white mb-1">
              {isLocked ? 'INTERLOCK LOCKED' : 'NORMAL ACCESS'}
            </div>
            <p className="text-xs text-slate-400">
              {isLocked ? 'Servo engaged; audible alarm pulsed' : 'Perimeter clear; gate servo open'}
            </p>
          </div>

          {/* Active Violations Gauge */}
          <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-mono uppercase tracking-wider text-slate-400">Total Breach Incidents</span>
              <div className="p-2 bg-orange-500/10 text-orange-400 rounded-lg">
                <AlertTriangle className="w-5 h-5" />
              </div>
            </div>
            <div className="text-2xl font-bold tracking-tight text-white mb-1">
              {stats.total_incidents || incidents.length}
            </div>
            <p className="text-xs text-slate-400">Hazard perimeter non-compliant events</p>
          </div>

          {/* Vision Verifications */}
          <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-mono uppercase tracking-wider text-slate-400">Vision Checks Processed</span>
              <div className="p-2 bg-blue-500/10 text-blue-400 rounded-lg">
                <Activity className="w-5 h-5" />
              </div>
            </div>
            <div className="text-2xl font-bold tracking-tight text-white mb-1">
              {stats.total_checks || (incidents.length * 4 + 12)}
            </div>
            <p className="text-xs text-slate-400">YOLOv8 + Homography evaluations</p>
          </div>

          {/* Telematics Protocol */}
          <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-mono uppercase tracking-wider text-slate-400">Telematics Protocol</span>
              <div className="p-2 bg-purple-500/10 text-purple-400 rounded-lg">
                <Layers className="w-5 h-5" />
              </div>
            </div>
            <div className="text-base font-bold font-mono tracking-tight text-purple-300 mb-1">
              CRC-16-CCITT
            </div>
            <p className="text-xs text-slate-400">10-Byte binary packet HAL framing</p>
          </div>
        </div>

        {/* Breach Alert Banner when Active */}
        {isLocked && (
          <div className="p-4 rounded-xl bg-gradient-to-r from-red-900/50 to-orange-950/40 border border-red-500/60 flex items-center justify-between animate-pulse-fast">
            <div className="flex items-center space-x-3">
              <ShieldAlert className="w-6 h-6 text-red-400 flex-shrink-0" />
              <div>
                <span className="font-bold text-red-200">PERIMETER HAZARD BREACH IN PROGRESS</span>
                <p className="text-xs text-red-300">
                  Worker detected inside dynamic hazard polygon lacking mandatory safety equipment.
                </p>
              </div>
            </div>
            <div className="flex items-center space-x-2 text-xs font-mono text-red-300 bg-red-950 px-3 py-1.5 rounded-lg border border-red-800">
              <Volume2 className="w-4 h-4 text-red-400" />
              <span>BUZZER PULSING</span>
            </div>
          </div>
        )}

        {/* Main Incident Feed & Snapshot Viewer */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Column: Live Edge Camera Stream & Incident Log Feed */}
          <div className="lg:col-span-2 space-y-6">
            {/* Live Edge Camera Stream Card */}
            <LiveCameraStream />

            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <Clock className="w-4 h-4 text-slate-400" />
                  <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
                    Incident Telemetry Feed ({filteredIncidents.length})
                  </h2>
                </div>
              <div className="flex space-x-2">
                <button
                  onClick={() => setFilterZone('ALL')}
                  className={`px-2.5 py-1 text-xs rounded-md transition ${
                    filterZone === 'ALL' ? 'bg-slate-700 text-white' : 'bg-slate-900 text-slate-400 hover:text-white'
                  }`}
                >
                  All Zones
                </button>
                <button
                  onClick={() => setFilterZone('HAZARD_ZONE_A1_EXCAVATION')}
                  className={`px-2.5 py-1 text-xs rounded-md transition ${
                    filterZone === 'HAZARD_ZONE_A1_EXCAVATION' ? 'bg-slate-700 text-white' : 'bg-slate-900 text-slate-400 hover:text-white'
                  }`}
                >
                  Excavation Zone
                </button>
              </div>
            </div>

            {filteredIncidents.length === 0 ? (
              <div className="p-12 rounded-2xl bg-slate-900/40 border border-slate-800 text-center space-y-3">
                <ShieldCheck className="w-12 h-12 text-emerald-500/60 mx-auto" />
                <h3 className="text-base font-semibold text-slate-300">No Perimeter Violations Recorded</h3>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  The hazard zone is clear and all detected personnel are fully compliant with mandatory safety gear.
                </p>
              </div>
            ) : (
              <div className="space-y-3 max-h-[600px] overflow-y-auto pr-2">
                {filteredIncidents.map((incident, idx) => {
                  const isSelected = selectedIncident && selectedIncident.id === incident.id;
                  return (
                    <div
                      key={incident.id || idx}
                      onClick={() => setSelectedIncident(incident)}
                      className={`p-4 rounded-xl border cursor-pointer transition-all ${
                        isSelected 
                          ? 'bg-slate-800/80 border-orange-500/50 shadow-md' 
                          : 'bg-slate-900/50 border-slate-800 hover:bg-slate-800/40 hover:border-slate-700'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center space-x-2">
                          <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-ping" />
                          <span className="text-xs font-mono font-bold text-red-400">
                            {incident.compliance_status || 'VIOLATION'}
                          </span>
                          <span className="text-xs text-slate-500 font-mono">
                            ID #{incident.id || idx + 1}
                          </span>
                        </div>
                        <span className="text-xs text-slate-400 font-mono">
                          {incident.iso_timestamp || new Date().toLocaleTimeString()}
                        </span>
                      </div>

                      <div className="grid grid-cols-2 gap-2 text-xs text-slate-300 my-2">
                        <div>
                          <span className="text-slate-500">Subject: </span>
                          <span className="font-semibold text-white">Person #{incident.person_id}</span>
                        </div>
                        <div>
                          <span className="text-slate-500">Zone: </span>
                          <span className="font-mono text-orange-400">{incident.zone_id}</span>
                        </div>
                        <div>
                          <span className="text-slate-500">Missing PPE: </span>
                          <span className="font-bold text-red-400">
                            {Array.isArray(incident.missing_gear) 
                              ? incident.missing_gear.join(', ').toUpperCase() 
                              : (incident.missing_gear || 'HELMET')}
                          </span>
                        </div>
                        <div>
                          <span className="text-slate-500">Ground Contact: </span>
                          <span className="font-mono text-blue-300">
                            {incident.ground_position ? `(${incident.ground_position[0].toFixed(1)}m, ${incident.ground_position[1].toFixed(1)}m)` : 'Calibrated'}
                          </span>
                        </div>
                      </div>

                      {incident.snapshot_url && (
                        <div className="mt-2 text-xs text-orange-400 flex items-center space-x-1">
                          <Camera className="w-3.5 h-3.5" />
                          <span>Evidence snapshot captured (Click to inspect)</span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
            </div>
          </div>

          {/* Evidence Snapshot Inspector Panel */}
          <div className="space-y-4">
            <div className="flex items-center space-x-2">
              <Camera className="w-4 h-4 text-slate-400" />
              <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
                Evidence Snapshot Inspector
              </h2>
            </div>

            <div className="p-4 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-4">
              {selectedIncident ? (
                <div>
                  <div className="relative rounded-xl overflow-hidden bg-slate-950 border border-slate-800 aspect-video flex items-center justify-center mb-3">
                    {selectedIncident.snapshot_url ? (
                      <img
                        src={`${API_BASE}${selectedIncident.snapshot_url}`}
                        alt="Violation Evidence"
                        className="w-full h-full object-contain"
                        onError={(e) => {
                          e.target.style.display = 'none';
                        }}
                      />
                    ) : (
                      <div className="text-center p-6 text-slate-500 space-y-2">
                        <Camera className="w-8 h-8 mx-auto text-slate-600" />
                        <p className="text-xs">Edge snapshot cached locally in edge_engine/evidence_snapshots/</p>
                      </div>
                    )}
                  </div>

                  <div className="space-y-2 text-xs font-mono">
                    <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800">
                      <div className="text-slate-500 mb-1">Zone Identifier:</div>
                      <div className="text-orange-400 font-bold">{selectedIncident.zone_id}</div>
                    </div>

                    <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800">
                      <div className="text-slate-500 mb-1">Missing Mandatory Equipment:</div>
                      <div className="text-red-400 font-bold">
                        {Array.isArray(selectedIncident.missing_gear) 
                          ? selectedIncident.missing_gear.join(', ').toUpperCase() 
                          : selectedIncident.missing_gear}
                      </div>
                    </div>

                    <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800">
                      <div className="text-slate-500 mb-1">Homography Ground Position:</div>
                      <div className="text-cyan-400">
                        {selectedIncident.ground_position ? `X: ${selectedIncident.ground_position[0]}m | Y: ${selectedIncident.ground_position[1]}m` : 'Calibrated'}
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="p-10 text-center text-slate-500 space-y-2">
                  <MapPin className="w-8 h-8 mx-auto text-slate-600" />
                  <p className="text-xs">Select any incident from the telemetry feed to inspect detailed evidence.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800/80 bg-slate-950 px-6 py-4 text-center text-xs text-slate-500">
        Autonomous PPE Verification & Perimeter Access Control System &bull; Edge Engine & Cloud Hub Architecture
      </footer>
    </div>
  );
}
