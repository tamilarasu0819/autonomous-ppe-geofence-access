import React, { useState, useEffect, useRef } from 'react';
import { 
  Video, 
  Play, 
  Pause, 
  RefreshCw, 
  AlertCircle, 
  Square, 
  PowerOff, 
  Upload, 
  FileVideo, 
  Film, 
  CheckCircle2, 
  Loader2 
} from 'lucide-react';

const API_BASE = "http://127.0.0.1:8000";
const STREAM_URL = `${API_BASE}/api/stream/video`;

export default function LiveCameraStream() {
  const [activeTab, setActiveTab] = useState('webcam'); // 'webcam' | 'file'
  const [isEngineRunning, setIsEngineRunning] = useState(false);
  const [isOperating, setIsOperating] = useState(false);
  const [isPlaying, setIsPlaying] = useState(true);
  const [isMirrored, setIsMirrored] = useState(false);
  const [qualityMode, setQualityMode] = useState("fast");
  const [streamError, setStreamError] = useState(false);
  const [streamTimestamp, setStreamTimestamp] = useState(Date.now());

  // Video file upload states
  const [selectedFile, setSelectedFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState("");
  const [activeSourceName, setActiveSourceName] = useState("Webcam (Device 0)");
  const fileInputRef = useRef(null);

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

  // Fetch initial stream quality configuration
  const fetchConfig = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/edge/config`);
      if (res.ok) {
        const data = await res.json();
        if (data.quality) {
          setQualityMode(data.quality);
        }
      }
    } catch (err) {
      // Backend offline
    }
  };

  useEffect(() => {
    checkEdgeStatus();
    fetchConfig();
    const interval = setInterval(checkEdgeStatus, 2500);
    return () => clearInterval(interval);
  }, []);

  // Update dynamic quality configuration
  const handleQualityChange = async (mode) => {
    setQualityMode(mode);
    try {
      await fetch(`${API_BASE}/api/edge/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode })
      });
    } catch (err) {
      console.error("Failed to update stream quality:", err);
    }
  };

  // Start / Stop Camera Engine for Live Webcam
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
        const res = await fetch(`${API_BASE}/api/edge/start`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ source_type: "webcam" })
        });
        if (res.ok) {
          setIsEngineRunning(true);
          setIsPlaying(true);
          setStreamError(false);
          setStreamTimestamp(Date.now());
          setActiveSourceName("Webcam (Device 0)");
        }
      }
    } catch (err) {
      console.error("Failed to toggle edge camera engine:", err);
    } finally {
      setIsOperating(false);
      setTimeout(checkEdgeStatus, 1000);
    }
  };

  // Handle local video file selection
  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setSelectedFile(file);
      setUploadStatus(`Selected: ${file.name} (${(file.size / (1024 * 1024)).toFixed(1)} MB)`);
    }
  };

  // Upload video and trigger analysis
  const handleUploadAndAnalyze = async () => {
    if (!selectedFile) {
      alert("Please select a video file (.mp4, .avi, .mov) to analyze.");
      return;
    }

    setIsUploading(true);
    setIsOperating(true);
    setUploadStatus("Uploading video file to backend...");

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);

      // Step 1: Post video file to http://127.0.0.1:8000/api/video/upload
      const uploadRes = await fetch(`${API_BASE}/api/video/upload`, {
        method: "POST",
        body: formData
      });

      if (!uploadRes.ok) {
        throw new Error(`Upload failed with status code ${uploadRes.status}`);
      }

      const uploadData = await uploadRes.json();
      setUploadStatus(`Uploaded successfully. Starting vision analysis on ${uploadData.filepath}...`);

      // Step 2: Call POST http://127.0.0.1:8000/api/edge/start with file configuration
      const startRes = await fetch(`${API_BASE}/api/edge/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_type: "file",
          file_path: uploadData.filepath
        })
      });

      if (startRes.ok) {
        setIsEngineRunning(true);
        setIsPlaying(true);
        setStreamError(false);
        setStreamTimestamp(Date.now());
        setActiveSourceName(selectedFile.name);
        setUploadStatus("Video analysis active. Streaming annotated frames.");
      } else {
        throw new Error("Failed to start edge engine subprocess on video file.");
      }
    } catch (err) {
      console.error("Video upload & analysis error:", err);
      setUploadStatus(`Error: ${err.message}`);
    } finally {
      setIsUploading(false);
      setIsOperating(false);
      setTimeout(checkEdgeStatus, 1200);
    }
  };

  const handleToggleStream = () => {
    if (!isPlaying) {
      setStreamError(false);
      setStreamTimestamp(Date.now());
    }
    setIsPlaying(!isPlaying);
  };

  const handleRefresh = () => {
    setStreamError(false);
    setStreamTimestamp(Date.now());
    setIsPlaying(true);
    checkEdgeStatus();
    fetchConfig();
  };

  return (
    <div className="rounded-2xl bg-slate-900/60 border border-slate-800 p-4 space-y-3.5">
      {/* Stream Card Header & Mode Switcher */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-2 border-b border-slate-800/80">
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
              <span>Live Edge Vision Stream</span>
            </h2>
            <p className="text-xs text-slate-400">YOLOv8 Annotations & Geofence Overlay</p>
          </div>
        </div>

        {/* Mode Switcher Tabs */}
        <div className="inline-flex rounded-xl p-1 bg-slate-950 border border-slate-800">
          <button
            onClick={() => setActiveTab('webcam')}
            className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
              activeTab === 'webcam'
                ? 'bg-orange-600 text-white shadow-md'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <Video className="w-3.5 h-3.5" />
            <span>📷 Live Camera Feed</span>
          </button>
          <button
            onClick={() => setActiveTab('file')}
            className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
              activeTab === 'file'
                ? 'bg-orange-600 text-white shadow-md'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <Film className="w-3.5 h-3.5" />
            <span>📁 Upload Video</span>
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Status Pill */}
          {isEngineRunning ? (
            <div className="flex items-center space-x-2 px-2.5 py-1 rounded-full bg-emerald-950/60 border border-emerald-500/40 text-emerald-400 text-xs font-mono">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <span>FEED ACTIVE ({activeSourceName.length > 18 ? activeSourceName.substring(0, 16) + '...' : activeSourceName})</span>
            </div>
          ) : (
            <div className="flex items-center space-x-2 px-2.5 py-1 rounded-full bg-slate-800/80 border border-slate-700 text-slate-400 text-xs font-mono">
              <span className="w-2 h-2 rounded-full bg-slate-500" />
              <span>ENGINE STOPPED</span>
            </div>
          )}

          {/* Interactive Stop Button when Running */}
          {isEngineRunning && (
            <button
              onClick={toggleCameraEngine}
              disabled={isOperating}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white shadow-sm shadow-red-950/40"
            >
              <Square className="w-3.5 h-3.5 fill-current" />
              <span>{isOperating ? "Stopping..." : "Stop Engine"}</span>
            </button>
          )}

          {/* Pause / Resume Button */}
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
                  <span>Pause</span>
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5" />
                  <span>Resume</span>
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

      {/* Quality Mode & Mirroring Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2.5 pt-1 pb-1">
        {/* Quality Mode Button Group */}
        <div className="flex items-center space-x-2">
          <span className="text-xs text-slate-400 font-mono">Inference Speed:</span>
          <div className="inline-flex rounded-lg p-0.5 bg-slate-950 border border-slate-800">
            <button
              onClick={() => handleQualityChange("fast")}
              className={`px-2.5 py-1 text-xs font-semibold rounded-md transition ${
                qualityMode === "fast"
                  ? "bg-orange-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              ⚡ Fast (30+ FPS)
            </button>
            <button
              onClick={() => handleQualityChange("balanced")}
              className={`px-2.5 py-1 text-xs font-semibold rounded-md transition ${
                qualityMode === "balanced"
                  ? "bg-orange-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              ⚖️ Balanced
            </button>
            <button
              onClick={() => handleQualityChange("hd")}
              className={`px-2.5 py-1 text-xs font-semibold rounded-md transition ${
                qualityMode === "hd"
                  ? "bg-orange-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              🎬 High Res
            </button>
          </div>
        </div>

        {/* Mirror Toggle Button */}
        <div>
          <button
            onClick={() => setIsMirrored(!isMirrored)}
            className="px-3 py-1 bg-slate-800 rounded text-xs border border-slate-700 hover:bg-slate-700 transition text-slate-200"
          >
            {isMirrored ? "🪞 Mirrored (Selfie)" : "📷 Normal Orientation"}
          </button>
        </div>
      </div>

      {/* Main Stream Viewer / Tab Control Container */}
      <div className="relative rounded-xl overflow-hidden bg-slate-950 border border-slate-800 aspect-video flex items-center justify-center">
        {isEngineRunning ? (
          /* Active Live Stream Video Viewer */
          isPlaying ? (
            <>
              <img
                key={streamTimestamp}
                src={`http://127.0.0.1:8000/api/stream/video?t=${streamTimestamp}`}
                alt="Live Stream"
                className={`w-full h-auto rounded-lg border border-slate-700 bg-slate-900 object-cover transition-transform duration-200 ${isMirrored ? "-scale-x-100" : ""}`}
                onError={() => setStreamError(true)}
                onLoad={() => setStreamError(false)}
              />

              {streamError && (
                <div className="absolute inset-0 bg-slate-950/90 backdrop-blur-sm flex flex-col items-center justify-center p-6 text-center space-y-2.5">
                  <AlertCircle className="w-8 h-8 text-amber-400" />
                  <h4 className="text-sm font-semibold text-slate-200">Waiting for Stream Frames...</h4>
                  <p className="text-xs text-slate-400 max-w-md">
                    Edge process active. Loading video stream and YOLOv8 weights...
                  </p>
                  <button
                    onClick={handleRefresh}
                    className="mt-2 px-3 py-1.5 rounded-lg bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition"
                  >
                    Reconnect Stream
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
                  MJPEG streaming paused to save bandwidth while the edge analysis engine continues running.
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
          )
        ) : activeTab === 'webcam' ? (
          /* Inactive State: Live Webcam Mode */
          <div className="flex flex-col items-center justify-center p-8 text-center space-y-3.5 text-slate-400">
            <div className="p-3.5 bg-slate-900 border border-slate-800 rounded-2xl text-slate-500">
              <PowerOff className="w-8 h-8" />
            </div>
            <div className="space-y-1 max-w-md">
              <h4 className="text-sm font-semibold text-slate-200">Live Camera Engine Inactive</h4>
              <p className="text-xs text-slate-400">
                Click <span className="text-emerald-400 font-semibold">'Start Camera Engine'</span> to launch real-time webcam detection.
              </p>
            </div>
            <button
              onClick={toggleCameraEngine}
              disabled={isOperating}
              className="px-5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-xs font-bold text-white transition flex items-center space-x-2 shadow-lg shadow-emerald-950/40"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>{isOperating ? "Launching Engine..." : "Start Camera Engine"}</span>
            </button>
          </div>
        ) : (
          /* Inactive State: Video File Upload & Analyze Mode */
          <div className="flex flex-col items-center justify-center p-8 text-center space-y-4 text-slate-400 max-w-lg mx-auto">
            <div className="p-4 bg-slate-900 border border-slate-800 rounded-2xl text-orange-400 shadow-inner">
              <Film className="w-8 h-8" />
            </div>

            <div className="space-y-1">
              <h4 className="text-sm font-semibold text-slate-100">Analyze Offline Video Footage</h4>
              <p className="text-xs text-slate-400">
                Upload CCTV, drone, or mobile site videos to run autonomous PPE detection and hazard geofencing.
              </p>
            </div>

            {/* Hidden native file input */}
            <input
              ref={fileInputRef}
              type="file"
              accept="video/mp4,video/avi,video/mov,.mp4,.avi,.mov"
              onChange={handleFileChange}
              className="hidden"
            />

            {/* File selection box */}
            <div 
              onClick={() => fileInputRef.current && fileInputRef.current.click()}
              className="w-full p-4 rounded-xl border border-dashed border-slate-700 bg-slate-900/50 hover:bg-slate-900 hover:border-orange-500/50 transition cursor-pointer flex flex-col items-center space-y-2"
            >
              <Upload className="w-5 h-5 text-slate-400" />
              {selectedFile ? (
                <div className="flex items-center space-x-2 text-xs text-emerald-400 font-mono">
                  <CheckCircle2 className="w-4 h-4" />
                  <span className="font-semibold">{selectedFile.name}</span>
                  <span className="text-slate-500">({(selectedFile.size / (1024 * 1024)).toFixed(1)} MB)</span>
                </div>
              ) : (
                <div className="space-y-0.5 text-center">
                  <p className="text-xs text-slate-300 font-medium">Click to select MP4, AVI, or MOV video</p>
                  <p className="text-[11px] text-slate-500 font-mono">Loops continuously during edge analysis</p>
                </div>
              )}
            </div>

            {/* Status message */}
            {uploadStatus && (
              <p className="text-xs font-mono text-orange-300 animate-fade-in">{uploadStatus}</p>
            )}

            {/* Analyze Button */}
            <button
              onClick={handleUploadAndAnalyze}
              disabled={isOperating || isUploading || !selectedFile}
              className="px-6 py-2.5 rounded-xl bg-orange-600 hover:bg-orange-500 disabled:opacity-50 disabled:hover:bg-orange-600 text-xs font-bold text-white transition flex items-center space-x-2 shadow-lg shadow-orange-950/40"
            >
              {isUploading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Uploading & Starting Analysis...</span>
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5 fill-current" />
                  <span>Analyze Uploaded Video</span>
                </>
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
