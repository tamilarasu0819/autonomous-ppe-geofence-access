import React, { useState, useEffect } from 'react';
import { Video, Play, Pause, RefreshCw, AlertCircle, Square, Power, PowerOff, Cpu } from 'lucide-react';

const API_BASE = "http://127.0.0.1:8000";
const STREAM_URL = `${API_BASE}/api/stream/video`;

export default function LiveCameraStream() {
  const [isEngineRunning, setIsEngineRunning] = useState(false);
  const [isOperating, setIsOperating] = useState(false);
  const [isPlaying, setIsPlaying] = useState(true);
  const [streamError, setStreamError] = useState(false);
  const [key, setKey] = useState(Date.now()); // Hard refresh key for MJPEG reconnect

  // Sync edge engine status with backend
  const checkEdgeStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/edge/status`);
      if (res.ok) {
        const data = await res.json();
        setIsEngineRunning(data.running);
      }
    } catch (err) {
      // Backend offline or starting up
    }
  };

  useEffect(() => {
    checkEdgeStatus();
    const interval = setInterval(checkEdgeStatus, 2500);
    return () => clearInterval(interval);
  }, []);

  // Start / Stop Camera Engine
  const toggleCameraEngine = async () => {
    setIsOperating(true);
    try {
      if (isEngineRunning) {
        const res = await fetch(`${API_BASE}/api/edge/stop`, { method: "POST" });
        if (res.ok) {
          setIsEngineRunning(false);
          setStreamError(false);
        }
      } else {
        const res = await fetch(`${API_BASE}/api/edge/start`, { method: "POST" });
        if (res.ok) {
          setIsEngineRunning(true);
          setIsPlaying(true);
          setStreamError(false);
          setKey(Date.now());
        }
      }
    } catch (err) {
      console.error("Failed to toggle edge camera engine:", err);
    } finally {
      setIsOperating(false);
      setTimeout(checkEdgeStatus, 1000);
    }
  };

  const handleToggleStream = () => {
    if (!isPlaying) {
      setStreamError(false);
      setKey(Date.now());
    }
    setIsPlaying(!isPlaying);
  };

  const handleRefresh = () => {
    setStreamError(false);
    setKey(Date.now());
    setIsPlaying(true);
    checkEdgeStatus();
  };

  return (
    <div className="rounded-2xl bg-slate-900/60 border border-slate-800 p-4 space-y-3">
      {/* Stream Card Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center space-x-2.5">
          <div className={`p-2 rounded-lg border transition-colors ${
            isEngineRunning 
              ? 'bg-orange-500/10 border-orange-500/30 text-orange-400' 
              : 'bg-slate-800 border-slate-700 text-slate-400'
          }`}>
            <Video className="w-4 h-4" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-white tracking-wide uppercase flex items-center space-x-2">
              <span>Live Edge Camera Stream</span>
            </h2>
            <p className="text-xs text-slate-400">YOLOv8 Annotations & Geofence Overlay</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Status Pill */}
          {isEngineRunning ? (
            <div className="flex items-center space-x-2 px-2.5 py-1 rounded-full bg-emerald-950/60 border border-emerald-500/40 text-emerald-400 text-xs font-mono">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <span>EDGE FEED ACTIVE (LOCAL MOCK)</span>
            </div>
          ) : (
            <div className="flex items-center space-x-2 px-2.5 py-1 rounded-full bg-slate-800/80 border border-slate-700 text-slate-400 text-xs font-mono">
              <span className="w-2 h-2 rounded-full bg-slate-500" />
              <span>CAMERA ENGINE STOPPED</span>
            </div>
          )}

          {/* Interactive Start / Stop Camera Engine Button */}
          {isEngineRunning ? (
            <button
              onClick={toggleCameraEngine}
              disabled={isOperating}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white shadow-sm shadow-red-950/40"
            >
              <Square className="w-3.5 h-3.5 fill-current" />
              <span>{isOperating ? "Stopping..." : "Stop Camera Engine"}</span>
            </button>
          ) : (
            <button
              onClick={toggleCameraEngine}
              disabled={isOperating}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white shadow-sm shadow-emerald-950/40"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>{isOperating ? "Launching..." : "Start Camera Engine"}</span>
            </button>
          )}

          {/* Pause / Resume Button (Only visible when engine is running) */}
          {isEngineRunning && (
            <button
              onClick={handleToggleStream}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition border ${
                isPlaying
                  ? 'bg-amber-950/40 border-amber-600/40 text-amber-300 hover:bg-amber-900/50'
                  : 'bg-emerald-950/40 border-emerald-600/40 text-emerald-300 hover:bg-emerald-900/50'
              }`}
            >
              {isPlaying ? (
                <>
                  <Pause className="w-3.5 h-3.5" />
                  <span>Pause Stream</span>
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5" />
                  <span>Resume Stream</span>
                </>
              )}
            </button>
          )}

          {/* Reconnect button */}
          <button
            onClick={handleRefresh}
            title="Refresh stream connection"
            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 transition"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Stream Viewer Container */}
      <div className="relative rounded-xl overflow-hidden bg-slate-950 border border-slate-800 aspect-video flex items-center justify-center">
        {!isEngineRunning ? (
          /* Centered Placeholder when Engine is Inactive */
          <div className="flex flex-col items-center justify-center p-8 text-center space-y-3.5 text-slate-400">
            <div className="p-3.5 bg-slate-900 border border-slate-800 rounded-2xl text-slate-500">
              <PowerOff className="w-8 h-8" />
            </div>
            <div className="space-y-1 max-w-md">
              <h4 className="text-sm font-semibold text-slate-200">Camera Engine Inactive</h4>
              <p className="text-xs text-slate-400">
                Camera Engine Inactive. Click <span className="text-emerald-400 font-semibold">'Start Camera Engine'</span> to launch edge detection.
              </p>
            </div>
            <button
              onClick={toggleCameraEngine}
              disabled={isOperating}
              className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-xs font-bold text-white transition flex items-center space-x-2 shadow-lg shadow-emerald-950/40"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>{isOperating ? "Starting..." : "Start Camera Engine"}</span>
            </button>
          </div>
        ) : isPlaying ? (
          <>
            <img
              key={key}
              src={`${STREAM_URL}?t=${key}`}
              alt="Live Stream"
              className="w-full h-auto rounded-lg border border-slate-700 bg-slate-900 object-cover"
              onError={() => setStreamError(true)}
              onLoad={() => setStreamError(false)}
            />

            {streamError && (
              <div className="absolute inset-0 bg-slate-950/90 backdrop-blur-sm flex flex-col items-center justify-center p-6 text-center space-y-2.5">
                <AlertCircle className="w-8 h-8 text-amber-400" />
                <h4 className="text-sm font-semibold text-slate-200">Waiting for Camera Frames...</h4>
                <p className="text-xs text-slate-400 max-w-md">
                  Edge process started. Initializing camera stream and YOLOv8 weights...
                </p>
                <button
                  onClick={handleRefresh}
                  className="mt-2 px-3 py-1.5 rounded-lg bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition"
                >
                  Reconnect
                </button>
              </div>
            )}
          </>
        ) : (
          /* Stream Paused Viewer */
          <div className="flex flex-col items-center justify-center p-8 text-center space-y-3 text-slate-500">
            <Video className="w-10 h-10 text-slate-600" />
            <div className="space-y-1">
              <h4 className="text-sm font-semibold text-slate-300">Stream Paused</h4>
              <p className="text-xs text-slate-500 max-w-sm">
                Live MJPEG video streaming is paused to save network bandwidth while engine runs.
              </p>
            </div>
            <button
              onClick={handleToggleStream}
              className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-xs font-bold text-white transition flex items-center space-x-1.5"
            >
              <Play className="w-4 h-4" />
              <span>Resume Live Stream</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
