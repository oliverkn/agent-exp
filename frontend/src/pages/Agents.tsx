import React, { useEffect, useState, useRef } from 'react';
import axios from 'axios';
import type { Timeout } from 'node';
import DOMPurify from 'dompurify';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface Thread {
  id: number;
  title: string;
  created_at: string;
}

interface Message {
  id: number;
  role: 'assistant' | 'tool' | 'user' | 'developer';
  content?: string;
  content_type?: string;
  agent_state?: string;
  created_at: string;
  tool_name?: string;
  tool_call_id?: string;
  tool_result?: string;
  tool_args?: string;
}

const ToolMessage = ({ message }: { message: Message }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [selectedImage, setSelectedImage] = useState<string | null>(null);

  const renderToolContent = () => {
    if (!message.content) return null;

    // Handle view_pdf_attachment tool which returns images
    if (message.content_type === 'image_url_list') {
      try {
        const imageUrls = JSON.parse(message.content);
        return (
          <>
            <div className="mt-4 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
              {imageUrls.map((url: string, index: number) => (
                <div key={index} className="relative cursor-pointer">
                  <img 
                    src={url} 
                    alt={`PDF page ${index + 1}`}
                    className="w-32 h-32 object-contain rounded-lg shadow-md hover:shadow-lg transition-shadow"
                    loading="lazy"
                    onClick={() => setSelectedImage(url)}
                  />
                </div>
              ))}
            </div>
            {selectedImage && (
              <div 
                className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50 p-4"
                onClick={() => setSelectedImage(null)}
              >
                <img 
                  src={selectedImage} 
                  alt="Full size"
                  className="max-w-full max-h-full object-contain"
                />
              </div>
            )}
          </>
        );
      } catch (e) {
        console.error('Error parsing image URLs:', e);
        return <div className="text-red-500">Error displaying PDF pages</div>;
      }
    }

    // Default content rendering
    return (
      <div className="mt-1" dangerouslySetInnerHTML={{ __html: message.content }} />
    );
  };

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="text-sm text-gray-600 hover:text-gray-800 flex-shrink-0"
        >
          {isExpanded ? '▼' : '▶'}
        </button>
        <div className="min-w-0 flex-1">
          <div className="font-medium">
            {message.tool_name || 'Tool'}
          </div>
          <div className="whitespace-pre-wrap break-all">
            {renderToolContent()}
          </div>
        </div>
      </div>

      {isExpanded && (
        <div className="ml-6 mt-2 space-y-2">
          {message.tool_args && (
            <div className="p-2 bg-green-50 rounded">
              <span className="font-medium">Args: </span>
              <div className="whitespace-pre-wrap break-all">
                {message.tool_args}
              </div>
            </div>
          )}
          {message.tool_result && (
            <div className="p-2 bg-green-50 rounded">
              <span className="font-medium">Result: </span>
              <div className="whitespace-pre-wrap break-all">
                {message.tool_result}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default function Agents() {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [selectedThread, setSelectedThread] = useState<Thread | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [newThreadTitle, setNewThreadTitle] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [newMessage, setNewMessage] = useState('');
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  // Auto scroll when messages change
  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const API_BASE_URL = 'http://localhost:8000';

  useEffect(() => {
    fetchThreads();
  }, []);

  // Fetch messages when thread is selected
  useEffect(() => {
    if (selectedThread) {
      fetchThreadMessages(selectedThread.id);
    }
  }, [selectedThread]);

  useEffect(() => {
    let ws: WebSocket;
    let pingInterval: ReturnType<typeof setInterval>;
    
    if (selectedThread) {
        const wsUrl = API_BASE_URL.replace('http://', 'ws://');
        console.log('Attempting to connect to WebSocket:', `${wsUrl}/ws/${selectedThread.id}`);
        
        try {
            ws = new WebSocket(`${wsUrl}/ws/${selectedThread.id}`);
            
            ws.onopen = () => {
                console.log('WebSocket connected successfully');
                // Start ping-pong to keep connection alive
                pingInterval = setInterval(() => {
                    if (ws.readyState === WebSocket.OPEN) {
                        ws.send('ping');
                    }
                }, 30000); // Send ping every 30 seconds
            };
            
            ws.onmessage = async (event) => {
                try {
                    console.log('Raw WebSocket message received:', event.data);
                    
                    // Skip parsing for ping-pong messages
                    if (event.data === 'pong') {
                        console.log('Received pong response');
                        return;
                    }
                    
                    const data = JSON.parse(event.data);
                    console.log('Parsed WebSocket data:', data);
                    
                    // Handle both "type" and "event_type" formats
                    const eventType = data.event_type || data.type;
                    
                    if (eventType === 'message_insert' && data.message) {
                        console.log('New message received, adding to UI:', data.message);
                        addMessage(data.message);
                    } else if (eventType === 'message_update' && data.message) {
                        console.log('Message update received, updating UI:', data.message);
                        updateMessage(data.message);
                    } else {
                        console.log('Unhandled WebSocket message type:', data);
                    }
                } catch (error) {
                    console.error('Error processing WebSocket message:', error);
                    console.error('Raw message that caused error:', event.data);
                }
            };

            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
            
            ws.onclose = (event) => {
                console.log('WebSocket disconnected:', event.code, event.reason);
            };
        } catch (error) {
            console.error('Error creating WebSocket connection:', error);
        }
    }

    return () => {
        if (pingInterval) {
            clearInterval(pingInterval);
        }
        if (ws) {
            console.log('Cleaning up WebSocket connection');
            ws.close();
        }
    };
  }, [selectedThread]);

  const fetchThreads = async () => {
    try {
      setIsLoading(true);
      const response = await axios.get(`${API_BASE_URL}/api/threads/list`);
      setThreads(response.data);
    } catch (error) {
      setError('Failed to fetch threads');
      console.error('Error fetching threads:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const fetchThreadMessages = async (threadId: number) => {
    try {
        console.log('Fetching messages for thread:', threadId);
        const response = await axios.get(
            `${API_BASE_URL}/api/threads/${threadId}/get_thread_messages`
        );
        console.log('Received messages:', response.data);
        setMessages(response.data);
    } catch (error) {
        console.error('Error fetching messages:', error);
    }
  };

  const createThread = async () => {
    if (!newThreadTitle.trim()) {
      setError('Please enter a thread title');
      return;
    }

    try {
      setIsLoading(true);
      const response = await axios.post(`${API_BASE_URL}/api/threads/create`, {
        title: newThreadTitle
      });
      setThreads(prevThreads => [response.data, ...prevThreads]);
      setNewThreadTitle('');
    } catch (error) {
      setError('Failed to create thread');
      console.error('Error creating thread:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const sendMessage = async () => {
    if (!selectedThread || !newMessage.trim()) return;

    const messageContent = newMessage;
    setNewMessage('');
    setError(null); // Clear any previous errors

    try {
        const response = await axios.post(`${API_BASE_URL}/api/threads/${selectedThread.id}/message`, {
            content: messageContent
        });
        
        if (response.data.message) {
            setMessages(prevMessages => [...prevMessages, response.data.message]);
        }
    } catch (error: any) {
        console.error('Error sending message:', error);
        setNewMessage(messageContent);
        
        // Show user-friendly error message
        const errorMessage = error.response?.data?.detail || 
                           error.response?.data?.message || 
                           'Failed to send message. Please try again.';
        setError(errorMessage);
        
        // Optionally refresh messages to ensure consistency
        if (selectedThread) {
            await fetchThreadMessages(selectedThread.id);
        }
    }
  };

  const isAwaitingInput = messages.length > 0 && 
    messages[messages.length - 1].agent_state === 'await_input';

  const renderMessage = (message: Message) => {
    // Skip assistant messages that are tool calls or have no content
    if ((message.role === 'assistant' && message.tool_call_id) || 
        (message.role === 'assistant' && !message.content)) {
      return null;
    }

    const messageClasses = {
      assistant: 'bg-blue-50 text-blue-800',
      tool: 'bg-green-50 text-green-800',
      user: 'bg-gray-50 text-gray-800 whitespace-pre-wrap',
      developer: 'bg-purple-50 text-purple-800'
    };

    const renderContent = () => {
      if (!message.content) return null;

      if (message.content_type === 'image_url_list') {
        try {
          const imageUrls = JSON.parse(message.content);
          return (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
                {imageUrls.map((url: string, index: number) => (
                  <div key={index} className="relative cursor-pointer">
                    <img 
                      src={url} 
                      alt={`Generated image ${index + 1}`}
                      className="w-32 h-32 object-contain rounded-lg shadow-md hover:shadow-lg transition-shadow"
                      loading="lazy"
                      onClick={() => setSelectedImage(url)}
                    />
                  </div>
                ))}
              </div>
            </>
          );
        } catch (e) {
          console.error('Error parsing image URLs:', e);
          return <div className="text-red-500">Error displaying images</div>;
        }
      }

      // For assistant messages, use ReactMarkdown with GFM support
      if (message.role === 'assistant') {
        return (
          <div className="prose prose-blue max-w-none prose-pre:bg-gray-800 prose-pre:text-white prose-pre:p-4 prose-pre:rounded-lg">
            <ReactMarkdown 
              children={message.content}
              remarkPlugins={[remarkGfm]}
              components={{
                table: ({children}) => (
                  <table className="border-collapse border border-gray-300 my-4">{children}</table>
                ),
                thead: ({children}) => <thead>{children}</thead>,
                tbody: ({children}) => <tbody>{children}</tbody>,
                tr: ({children}) => <tr>{children}</tr>,
                th: ({children}) => (
                  <th className="border border-gray-300 px-4 py-2 bg-gray-100">{children}</th>
                ),
                td: ({children}) => (
                  <td className="border border-gray-300 px-4 py-2">{children}</td>
                ),
                code: ({node, inline, className, children, ...props}) => {
                  const match = /language-(\w+)/.exec(className || '');
                  return !inline ? (
                    <pre className="bg-gray-800 text-white p-4 rounded-lg">
                      <code className={className} {...props}>
                        {children}
                      </code>
                    </pre>
                  ) : (
                    <code className="bg-gray-100 rounded px-1" {...props}>
                      {children}
                    </code>
                  );
                }
              }}
            />
          </div>
        );
      }

      // For other message types, keep the existing sanitized HTML rendering
      const sanitizedContent = DOMPurify.sanitize(message.content);
      return (
        <div 
          className="mt-2 break-words overflow-hidden overflow-wrap-anywhere"
          style={{ wordBreak: 'break-word', overflowWrap: 'break-word', maxWidth: '100%' }}
          dangerouslySetInnerHTML={{ __html: sanitizedContent }}
        />
      );
    };

    return (
      <div className={`p-4 rounded-lg mb-4 ${messageClasses[message.role]} max-w-full`}>
        {message.role === 'tool' ? (
          <ToolMessage message={message} />
        ) : (
          <>
            <div className="font-medium capitalize">{message.role}</div>
            {renderContent()}
          </>
        )}
      </div>
    );
  };

  const addMessage = (msg: Message) => {
    console.log('Adding new message:', {
      message: msg,
      tool_args: msg.tool_args,
      tool_result: msg.tool_result,
      tool_name: msg.tool_name
    });
    
    setMessages(prevMessages => [...prevMessages, {
      ...msg,
      // Ensure tool-specific fields are explicitly included
      tool_args: msg.tool_args || undefined,
      tool_result: msg.tool_result || undefined,
      tool_name: msg.tool_name || undefined,
      tool_call_id: msg.tool_call_id || undefined
    }]);
  };

  const updateMessage = (updatedMsg: Message) => {
    console.log('Updating message:', {
      message: updatedMsg,
      tool_args: updatedMsg.tool_args,
      tool_result: updatedMsg.tool_result,
      tool_name: updatedMsg.tool_name
    });
    
    setMessages(prevMessages => 
      prevMessages.map(msg => {
        if (msg.id === updatedMsg.id) {
          return {
            ...msg,
            ...updatedMsg,
            // Explicitly preserve tool-specific fields
            tool_args: updatedMsg.tool_args || msg.tool_args,
            tool_result: updatedMsg.tool_result || msg.tool_result,
            tool_name: updatedMsg.tool_name || msg.tool_name,
            tool_call_id: updatedMsg.tool_call_id || msg.tool_call_id
          };
        }
        return msg;
      })
    );
  };

  const handleThreadSelect = async (thread: Thread) => {
    setSelectedThread(thread);
    setMessages([]); // Clear existing messages
    
    try {
        const response = await axios.get(
            `${API_BASE_URL}/api/threads/${thread.id}/get_thread_messages`
        );
        response.data.forEach((msg: Message) => {
            addMessage(msg);
        });
    } catch (error) {
        console.error('Error fetching messages:', error);
        setError('Failed to load messages');
    }
  };

  const renderThreadList = () => (
    <div className="space-y-2 overflow-y-auto">
      {threads.map((thread) => (
        <div
          key={thread.id}
          onClick={() => handleThreadSelect(thread)}
          className={`p-3 rounded-md cursor-pointer ${
            selectedThread?.id === thread.id
              ? 'bg-blue-100'
              : 'hover:bg-gray-100'
          }`}
        >
          <h3 className="font-medium">{thread.title}</h3>
          <p className="text-sm text-gray-500">
            {new Date(thread.created_at).toLocaleDateString()}
          </p>
        </div>
      ))}
    </div>
  );

  return (
    <div className="flex h-screen bg-gray-100">
      {/* Thread List Panel */}
      <div className="w-1/4 bg-white border-r border-gray-200 p-4 flex flex-col">
        <div className="mb-4">
          <input
            type="text"
            value={newThreadTitle}
            onChange={(e) => setNewThreadTitle(e.target.value)}
            placeholder="New Thread Title"
            className="w-full px-3 py-2 border border-gray-300 rounded-md mb-2"
          />
          <button
            onClick={createThread}
            disabled={isLoading}
            className="w-full px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
          >
            {isLoading ? 'Creating...' : 'Create Thread'}
          </button>
          {error && <div className="text-red-500 text-sm mt-2">{error}</div>}
        </div>

        {renderThreadList()}
      </div>

      {/* Messages Panel */}
      <div className="flex-1 flex flex-col">
        <div className="flex-1 overflow-y-auto p-4">
          {error && (
            <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative mb-4">
              {error}
            </div>
          )}
          {selectedThread ? (
            <div className="space-y-4">
              {messages.map((message, index) => (
                message && <div key={index}>{renderMessage(message)}</div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          ) : (
            <div className="flex items-center justify-center h-full text-gray-500">
              Select a thread to view messages
            </div>
          )}
          
          {/* Image Modal */}
          {selectedImage && (
            <div 
              className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50 p-4"
              onClick={() => setSelectedImage(null)}
            >
              <img 
                src={selectedImage} 
                alt="Full size"
                className="max-w-full max-h-full object-contain"
              />
            </div>
          )}
        </div>

        {/* Message Input */}
        {selectedThread && (
          <div className="p-4 border-t border-gray-200 bg-white">
            <div className="flex space-x-4">
              <textarea
                value={newMessage}
                onChange={(e) => setNewMessage(e.target.value)}
                disabled={!isAwaitingInput}
                placeholder={isAwaitingInput ? "Type your message..." : "Waiting for AI..."}
                className="flex-1 px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 resize-none h-[40px] min-h-[40px] max-h-[200px] overflow-y-hidden"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                  }
                }}
              />
              <button
                onClick={sendMessage}
                disabled={!isAwaitingInput || !newMessage.trim()}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
              >
                Send
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
} 