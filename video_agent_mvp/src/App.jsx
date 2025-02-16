import { useState, useRef, useEffect } from 'react'
import './App.css'

// Update the helper function to extract response text
const extractResponse = (text) => {
  if (!text) return '';
  
  // For streaming responses, keep the filtering
  if (!text.includes('Step-by-Step Instructions')) {
    const match = text.match(/Response:\s*([^]*?\.)/i);
    if (!match) return '';
    return match[1].trim();
  }
  
  // For final summary, just remove the "Response:" prefix
  return text.replace(/^Response:\s*/i, '').trim();
};

// Update the summary display component to be editable
const SummaryDisplay = ({ summary, onEdit }) => {
  console.log('Rendering SummaryDisplay with:', summary);
  return (
    <div className="final-summary">
      <h3>Process Automation Summary</h3>
      <div className="summary-timestamp">{summary.timestamp}</div>
      <div 
        className="summary-content" 
        contentEditable={true}
        suppressContentEditableWarning={true}
        onBlur={(e) => onEdit && onEdit(e.target.innerText)}
      >
        {summary.text}
      </div>
    </div>
  );
};

function App() {
  const [recording, setRecording] = useState(false)
  const [mediaRecorder, setMediaRecorder] = useState(null)
  const [recordedChunks, setRecordedChunks] = useState([])
  const [audioStream, setAudioStream] = useState(null)
  const [analysis, setAnalysis] = useState([])
  const [isConnected, setIsConnected] = useState(false)
  const [finalSummary, setFinalSummary] = useState(null)
  const [isProcessingSummary, setIsProcessingSummary] = useState(false)
  const wsRef = useRef(null)
  const speechSynthesisRef = useRef(null)

  // Initialize speech synthesis
  useEffect(() => {
    speechSynthesisRef.current = window.speechSynthesis;
    return () => {
      if (speechSynthesisRef.current) {
        speechSynthesisRef.current.cancel();
      }
    };
  }, []);

  // Function to speak text
  const speakText = (text) => {
    if (speechSynthesisRef.current) {
      speechSynthesisRef.current.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 1.0;
      utterance.pitch = 1.0;
      utterance.volume = 1.0;
      speechSynthesisRef.current.speak(utterance);
    }
  };

  // Move handleSummaryEdit outside of startRecording
  const handleSummaryEdit = (newText) => {
    setFinalSummary(prev => ({
      ...prev,
      text: newText
    }));
  };

  const startRecording = async () => {
    try {
      // Get system audio stream
      const audioStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: 44100
        }
      });
      
      // Get screen stream with audio
      const screenStream = await navigator.mediaDevices.getDisplayMedia({
        video: { 
          cursor: "always",
          frameRate: { ideal: 30 }
        },
        audio: true
      });

      // Combine streams
      const tracks = [...screenStream.getTracks()];
      audioStream.getAudioTracks().forEach(track => {
        tracks.push(track);
      });
      const combinedStream = new MediaStream(tracks);
      setAudioStream(audioStream);

      // Create media recorder with smaller chunk size
      const mediaRecorder = new MediaRecorder(combinedStream, {
        mimeType: 'video/webm;codecs=vp8,opus',
        videoBitsPerSecond: 500000, // Reduced to 500Kbps
        audioBitsPerSecond: 64000   // Reduced to 64Kbps
      });

      // Connect to WebSocket
      wsRef.current = new WebSocket('ws://localhost:8000/stream');
      
      wsRef.current.onopen = () => {
        console.log('WebSocket connected');
        setIsConnected(true);
      };

      // Update the WebSocket message handler
      wsRef.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log('WebSocket message received:', data);
          
          if (data.type === 'analysis') {
            if (data.is_summary) {
              console.log('Setting final summary:', data.content);
              setAnalysis([]);
              // Remove "Response:" prefix from the summary content
              const summaryText = data.content.replace(/^Response:\s*/i, '').trim();
              setFinalSummary({
                text: summaryText,
                timestamp: new Date().toLocaleTimeString()
              });
              setIsProcessingSummary(false);
            } else {
              // For streaming analysis, use the filtered response and speak it
              const responseText = extractResponse(data.content);
              if (responseText && responseText.length > 0) {
                const newAnalysis = {
                  text: responseText,
                  timestamp: new Date().toLocaleTimeString()
                };
                setAnalysis(prev => [...prev, newAnalysis]);
                
                if (speechSynthesisRef.current) {
                  const utterance = new SpeechSynthesisUtterance(responseText);
                  utterance.rate = 1.0;
                  utterance.pitch = 1.0;
                  utterance.volume = 1.0;
                  speechSynthesisRef.current.speak(utterance);
                }
              }
            }
          }
        } catch (error) {
          console.error('Error processing WebSocket message:', error);
          setIsProcessingSummary(false);
        }
      };

      wsRef.current.onerror = (error) => {
        console.error('WebSocket error:', error);
        setIsConnected(false);
      };

      wsRef.current.onclose = () => {
        console.log('WebSocket connection closed');
        setIsConnected(false);
      };

      // Send data more frequently
      mediaRecorder.ondataavailable = async (event) => {
        if (event.data.size > 0) {
          // Store for download
          setRecordedChunks((prev) => [...prev, event.data]);
          
          // Send to websocket if connected
          if (wsRef.current?.readyState === WebSocket.OPEN) {
            try {
              // Convert blob to ArrayBuffer before sending
              const arrayBuffer = await event.data.arrayBuffer();
              const uint8Array = new Uint8Array(arrayBuffer);
              
              // Only send if the data is not too large
              if (uint8Array.length > 512 * 1024) {
                // Take last 512KB if too large
                wsRef.current.send(uint8Array.slice(-512 * 1024));
              } else {
                wsRef.current.send(uint8Array);
              }
            } catch (error) {
              console.error("Error sending chunk:", error);
            }
          }
        }
      };

      // Start recording with smaller time slices
      mediaRecorder.start(100); // Capture every 100ms instead of 200ms
      setMediaRecorder(mediaRecorder);
      setRecording(true);

    } catch (error) {
      console.error("Error starting recording:", error);
      if (audioStream) {
        audioStream.getTracks().forEach(track => track.stop());
      }
    }
  };

  const stopRecording = () => {
    console.log('Stop recording clicked');
    setIsProcessingSummary(true);
    
    if (mediaRecorder) {
      mediaRecorder.stop();
      mediaRecorder.stream.getTracks().forEach(track => track.stop());
    }
    if (audioStream) {
      audioStream.getTracks().forEach(track => track.stop());
    }
    
    // Send stop recording message
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      console.log('Sending stop_recording message');
      wsRef.current.send(JSON.stringify({ type: 'stop_recording' }));
      
      setTimeout(() => {
        console.log('Closing WebSocket connection');
        if (wsRef.current) {
          wsRef.current.close();
        }
        if (speechSynthesisRef.current) {
          speechSynthesisRef.current.cancel();
        }
        setIsProcessingSummary(false);
      }, 10000);
    }
    
    setRecording(false);
    setAudioStream(null);
  };

  const downloadRecording = () => {
    if (recordedChunks.length === 0) return;

    const blob = new Blob(recordedChunks, {
      type: "video/webm"
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    document.body.appendChild(a);
    a.style = "display: none";
    a.href = url;
    a.download = `screen-recording-${new Date().toISOString()}.webm`;
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
    setRecordedChunks([]);
  };

  // Add LoadingSpinner component
  const LoadingSpinner = () => (
    <div className="loading-container">
      <div className="loading-spinner"></div>
      <div className="loading-text">Processing final summary...</div>
    </div>
  );

  return (
    <div className="app-wrapper">
      <div className="app-container">
        <h1>Welcome to Omakase</h1>
        {!recording && recordedChunks.length === 0 && (
          <h2>To automate a process just start recording it</h2>
        )}
        <div className="controls">
          {!recording && recordedChunks.length === 0 ? (
            <button onClick={startRecording}>Start Recording</button>
          ) : recording ? (
            <button onClick={stopRecording} className="stop-recording-btn">
              Stop Recording
            </button>
          ) : (
            <div className="post-recording-controls">
              <button onClick={() => {
                setRecordedChunks([]);
                setFinalSummary(null);
                setAnalysis([]);
                setIsProcessingSummary(false);
                startRecording();
              }} className="repeat-recording-btn">
                Repeat Recording
              </button>
              <button onClick={() => {
                setRecordedChunks([]);
                setFinalSummary(null);
                setAnalysis([]);
                setIsProcessingSummary(false);
              }} className="new-recording-btn">
                Record Another Process
              </button>
              <button onClick={downloadRecording}>
                Download Recording
              </button>
            </div>
          )}
        </div>
        {recording && (
          <div className="recording-controls">
            <div className="recording-indicator">
              🔴 Recording your process...
            </div>
          </div>
        )}
        {!recording && recordedChunks.length > 0 && (
          <div className="process-summary">
            <h3>Thank you for onboarding Omakase to your process </h3>
            <p>Please edit the summary on the right if you would like to make changes to the automated process.</p>
          </div>
        )}
      </div>
      <div className="side-panel">
        <div className={`recording-dot ${recording ? 'active' : ''}`} />
        <div className="analysis-container">
          {isProcessingSummary ? (
            <LoadingSpinner />
          ) : finalSummary ? (
            <SummaryDisplay 
              summary={finalSummary} 
              onEdit={handleSummaryEdit}
            />
          ) : analysis && analysis.length > 0 ? (
            // Show streaming analysis when recording
            <>
              <div className="connection-status">
                {isConnected ? '🟢 Connected' : '🔴 Disconnected'}
              </div>
              {analysis.map((item, index) => (
                <div key={index} className="analysis-item">
                  <div className="analysis-timestamp">{item.timestamp}</div>
                  <div className="analysis-text">{item.text}</div>
                </div>
              ))}
            </>
          ) : (
            recording && (
              <>
                <div className="connection-status">
                  {isConnected ? '🟢 Connected' : '🔴 Disconnected'}
                </div>
                <div className="analysis-text">Watching and analyzing your process...</div>
              </>
            )
          )}
        </div>
      </div>
    </div>
  );
}

export default App
