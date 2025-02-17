import React, { useEffect, useState, useRef } from 'react';
import axios from 'axios';
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

const ToolGroupMessage = ({ messages, allMessages }: { messages: Message[], allMessages: Message[] }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const latestMessage = messages[messages.length - 1];
  
  // Only check if the latest message in the entire conversation has await_input
  const hasAwaitInputAfter = allMessages.length > 0 && 
    allMessages[allMessages.length - 1].agent_state === 'await_input';

  return (
    <div className="space-y-2">
      <div className="min-w-0">
        <div className="font-medium flex justify-between items-center">
          <span>Took {messages.length} actions</span>
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-sm text-gray-400 hover:text-gray-600"
          >
            {isExpanded ? 'Hide details' : 'Show details'}
          </button>
        </div>
        {!isExpanded ? (
          !hasAwaitInputAfter ? (
            <div className="mt-2">
              <div className="font-medium text-gray-700">{latestMessage.tool_name}</div>
              <div className="mt-1 text-gray-600" dangerouslySetInnerHTML={{ __html: latestMessage.content || '' }} />
            </div>
          ) : null
        ) : (
          <div className="mt-4 space-y-4">
            {messages.map((message, index) => (
              <ToolMessage key={index} message={message} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

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
            <div className="mt-4 grid grid-cols-2 gap-4">
              {imageUrls.map((url: string, index: number) => (
                <div key={index} className="relative cursor-pointer flex items-center justify-start h-64">
                  <img 
                    src={url} 
                    alt={`PDF page ${index + 1}`}
                    className="max-h-full object-scale-down rounded-lg hover:shadow-lg transition-shadow border border-gray-200"
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
      <div className="min-w-0">
        <div className="font-medium">
          {message.tool_name || 'Tool'}
        </div>
        <div className="whitespace-pre-wrap break-all">
          {renderToolContent()}
        </div>
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="text-sm text-gray-400 hover:text-gray-600 mt-2"
        >
          {isExpanded ? 'Hide details' : 'Show details'}
        </button>
      </div>

      {isExpanded && (
        <div className="mt-4 space-y-3">
          {message.tool_args && (
            <div className="rounded-lg border border-gray-200 overflow-hidden">
              <div className="px-4 py-2 bg-gray-50 border-b border-gray-200">
                <span className="font-medium text-gray-700">Args:</span>
              </div>
              <div className="p-4 bg-white font-mono text-sm text-gray-800 whitespace-pre-wrap break-all">
                {message.tool_args}
              </div>
            </div>
          )}
          {message.tool_result && (
            <div className="rounded-lg border border-gray-200 overflow-hidden">
              <div className="px-4 py-2 bg-gray-50 border-b border-gray-200">
                <span className="font-medium text-gray-700">Result:</span>
              </div>
              <div className="p-4 bg-white font-mono text-sm text-gray-800 whitespace-pre-wrap break-all">
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
    // Skip messages that are empty, tool calls, or tool messages
    if (!message.content || 
        (message.role === 'assistant' && message.tool_call_id) || 
        message.role === 'tool' ||
        message.role === 'developer') {
      return null;
    }

    const messageClasses = {
      assistant: 'bg-white text-gray-900',
      user: 'bg-white text-gray-900 whitespace-pre-wrap',
    };

    const renderContent = () => {
      if (!message.content) return null;

      if (message.content_type === 'image_url_list') {
        try {
          const imageUrls = JSON.parse(message.content);
          if (!imageUrls || imageUrls.length === 0) return null;
          return (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
                {imageUrls.map((url: string, index: number) => (
                  <div key={index} className="relative cursor-pointer">
                    <img 
                      src={url} 
                      alt={`Generated image ${index + 1}`}
                      className="w-32 h-32 object-contain rounded-lg hover:shadow-lg transition-shadow border border-gray-200"
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
          return null;
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
                code: ({inline, className, children, ...props}: {
                  inline?: boolean;
                  className?: string;
                  children: React.ReactNode;
                }) => {
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
          className="break-words overflow-hidden overflow-wrap-anywhere"
          style={{ wordBreak: 'break-word', overflowWrap: 'break-word', maxWidth: '100%' }}
          dangerouslySetInnerHTML={{ __html: sanitizedContent }}
        />
      );
    };

    const content = renderContent();
    if (!content) return null;

    return (
      <>
        {content}
      </>
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

  return (
    <div className="flex h-screen bg-white">
      {/* Thread List Panel */}
      <div className="w-80 bg-white shadow-lg p-6 flex flex-col space-y-6 overflow-hidden">
        <div className="flex flex-col space-y-4">
          <input
            type="text"
            value={newThreadTitle}
            onChange={(e) => setNewThreadTitle(e.target.value)}
            placeholder="New Thread Title"
            className="w-full px-4 py-3 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
          />
          <button
            onClick={createThread}
            disabled={isLoading}
            className="w-full px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors font-medium"
          >
            {isLoading ? 'Creating...' : 'Create Thread'}
          </button>
          {error && <div className="text-gray-700 text-sm px-2">{error}</div>}
        </div>

        <div className="flex-1 overflow-y-auto space-y-3 -mr-4 pr-4">
          {threads.map((thread) => (
            <div
              key={thread.id}
              onClick={() => handleThreadSelect(thread)}
              className={`p-4 rounded-lg cursor-pointer transition-all ${
                selectedThread?.id === thread.id
                  ? 'border-2 border-gray-300'
                  : 'hover:bg-gray-50 border border-gray-200'
              }`}
            >
              <h3 className="font-medium text-gray-900 mb-1 truncate">{thread.title}</h3>
              <p className="text-sm text-gray-500">
                {new Date(thread.created_at).toLocaleDateString()}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Messages Panel */}
      <div className="flex-1 flex flex-col">
        {selectedThread && (
          <div className="px-8 py-4 bg-white shadow-sm border-b border-gray-100">
            <h2 className="text-xl font-semibold text-gray-900">{selectedThread.title}</h2>
          </div>
        )}
        
        <div className="flex-1 overflow-y-auto p-6 bg-gray-50">
          {error && (
            <div className="border border-gray-200 text-gray-700 px-4 py-3 rounded-lg mb-4">
              {error}
            </div>
          )}
          {selectedThread ? (
            <div className="space-y-4 max-w-3xl mx-auto pb-24">
              {(() => {
                const messageGroups: (Message | Message[])[] = [];
                let currentToolGroup: Message[] = [];

                console.log('Starting message grouping. Total messages:', messages.length);

                messages.forEach((message, index) => {
                  console.log(`Processing message ${index}:`, {
                    role: message.role,
                    content: message.content?.slice(0, 50),
                    tool_name: message.tool_name,
                    has_content: !!message.content
                  });

                  if (message.role === 'tool') {
                    console.log(`Adding message ${index} to tool group`);
                    currentToolGroup.push(message);
                  } else if (message.role === 'assistant' && !message.content) {
                    // Skip empty assistant messages (they're usually just tool call markers)
                    console.log(`Skipping empty assistant message ${index}`);
                  } else {
                    // If we have tool messages collected and we hit a non-tool message with content,
                    // add the tool group before adding this message
                    if (currentToolGroup.length > 0) {
                      console.log('Adding tool group to messageGroups:', currentToolGroup.length);
                      messageGroups.push([...currentToolGroup]);
                      currentToolGroup = [];
                    }
                    messageGroups.push(message);
                  }
                });

                // Add any remaining tool group
                if (currentToolGroup.length > 0) {
                  console.log('Adding final tool group:', currentToolGroup.length);
                  messageGroups.push([...currentToolGroup]);
                }

                console.log('Final message groups:', messageGroups.map(group => 
                  Array.isArray(group) ? `Tool group (${group.length})` : group.role
                ));

                return messageGroups.map((group, groupIndex) => {
                  if (Array.isArray(group)) {
                    // This is a tool message group
                    console.log(`Rendering tool group ${groupIndex} with ${group.length} messages`);
                    return (
                      <div key={`group-${groupIndex}`} className="transition-all w-full flex flex-col">
                        <div className="flex justify-start mb-2">
                          <div className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 font-medium text-base bg-emerald-100 text-emerald-700">
                            T
                          </div>
                        </div>
                        <div className="w-full">
                          <div className="bg-white rounded-xl px-4 py-3 w-full">
                            <ToolGroupMessage messages={group} allMessages={messages} />
                          </div>
                        </div>
                      </div>
                    );
                  } else {
                    // This is a single message
                    const messageContent = renderMessage(group);
                    if (!messageContent) return null;

                    return (
                      <div key={`message-${group.id}`} className="transition-all w-full flex flex-col">
                        <div className="flex justify-start mb-2">
                          <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 font-medium text-base ${
                            group.role === 'assistant' 
                              ? 'bg-purple-100 text-purple-700'
                              : group.role === 'user'
                              ? 'bg-blue-100 text-blue-700'
                              : 'bg-emerald-100 text-emerald-700'
                          }`}>
                            {group.role === 'assistant' ? 'A' : group.role === 'user' ? 'U' : 'T'}
                          </div>
                        </div>
                        <div className="w-full">
                          <div className="bg-white rounded-xl px-4 py-3 w-full">
                            {messageContent}
                          </div>
                        </div>
                      </div>
                    );
                  }
                });
              })()}
              <div ref={messagesEndRef} />
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-gray-500 space-y-4">
              <svg className="w-16 h-16 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
              <p className="text-lg font-medium">Select a thread to start chatting</p>
            </div>
          )}
          
          {/* Image Modal */}
          {selectedImage && (
            <div 
              className="fixed inset-0 bg-black bg-opacity-90 flex items-center justify-center z-50 p-4 backdrop-blur-sm"
              onClick={() => setSelectedImage(null)}
            >
              <img 
                src={selectedImage} 
                alt="Full size"
                className="max-w-full max-h-full object-contain rounded-lg"
              />
            </div>
          )}
        </div>

        {/* Message Input */}
        {selectedThread && (
          <div className="fixed bottom-6 left-[calc(320px+1.5rem)] right-6">
            <div className="max-w-3xl mx-auto px-0">
              <div className="flex space-x-4 bg-gray-900 rounded-xl p-4">
                <textarea
                  value={newMessage}
                  onChange={(e) => setNewMessage(e.target.value)}
                  disabled={!isAwaitingInput}
                  placeholder={isAwaitingInput ? "Type your message..." : "Waiting for AI..."}
                  className="flex-1 px-4 py-3 bg-gray-900 border-0 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-gray-100 placeholder-gray-400 disabled:bg-gray-800 disabled:text-gray-500 resize-none h-[48px] min-h-[48px] max-h-[200px] overflow-y-hidden"
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
                  className="w-12 h-12 bg-[#ddd] text-gray-500 rounded-full hover:bg-gray-200 disabled:opacity-50 transition-colors flex items-center justify-center flex-shrink-0"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
} 