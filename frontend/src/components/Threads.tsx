import React, { useEffect, useState, useRef } from 'react';
import { Message } from '../types';

interface ThreadsProps {
    selectedThreadId: number | null;
}

const Threads: React.FC<ThreadsProps> = ({ selectedThreadId }) => {
    const [messages, setMessages] = useState<Message[]>([]);
    const [isConnected, setIsConnected] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const wsRef = useRef<WebSocket | null>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    useEffect(() => {
        if (!selectedThreadId) return;

        // Clean up previous connection
        if (wsRef.current) {
            wsRef.current.close();
            setIsConnected(false);
        }

        // Create new WebSocket connection
        const ws = new WebSocket(`ws://localhost:8000/ws/${selectedThreadId}`);
        wsRef.current = ws;

        ws.onopen = () => {
            console.log('WebSocket connected');
            setIsConnected(true);
            setError(null);
        };

        ws.onmessage = (event) => {
            try {
                console.log('Received WebSocket message:', event.data);
                const message = JSON.parse(event.data);
                console.log('Parsed message:', message);

                if (message.type === 'message') {
                    setMessages(prevMessages => {
                        // Check if message already exists
                        if (prevMessages.some(m => m.id === message.id)) {
                            return prevMessages;
                        }
                        return [...prevMessages, message];
                    });
                }
            } catch (e) {
                console.error('Error processing WebSocket message:', e);
                setError('Error processing message');
            }
        };

        ws.onerror = (event) => {
            console.error('WebSocket error:', event);
            setError('WebSocket error occurred');
            setIsConnected(false);
        };

        ws.onclose = () => {
            console.log('WebSocket disconnected');
            setIsConnected(false);
        };

        // Fetch existing messages
        fetch(`http://localhost:8000/threads/${selectedThreadId}/messages`)
            .then(response => response.json())
            .then(data => {
                setMessages(data);
            })
            .catch(error => {
                console.error('Error fetching messages:', error);
                setError('Error fetching messages');
            });

        return () => {
            if (wsRef.current) {
                wsRef.current.close();
            }
        };
    }, [selectedThreadId]);

    const startAgent = async () => {
        if (!selectedThreadId) return;

        try {
            const response = await fetch(`http://localhost:8000/threads/${selectedThreadId}/start`, {
                method: 'POST'
            });
            
            if (!response.ok) {
                throw new Error('Failed to start agent');
            }
            
            console.log('Agent started successfully');
        } catch (error) {
            console.error('Error starting agent:', error);
            setError('Error starting agent');
        }
    };

    return (
        <div className="flex flex-col h-full">
            <div className="flex-grow overflow-y-auto p-4">
                {error && (
                    <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
                        {error}
                    </div>
                )}
                {messages.map((message, index) => (
                    <div
                        key={message.id || index}
                        className={`mb-4 p-4 rounded-lg ${
                            message.role === 'assistant' 
                                ? 'bg-blue-100 ml-auto' 
                                : message.role === 'user'
                                ? 'bg-gray-100'
                                : 'bg-yellow-100'
                        }`}
                    >
                        <div className="font-bold mb-2">{message.role}</div>
                        <div className="whitespace-pre-wrap">{message.content}</div>
                    </div>
                ))}
                <div ref={messagesEndRef} />
            </div>
            <div className="p-4 border-t">
                <button
                    onClick={startAgent}
                    disabled={!isConnected}
                    className={`px-4 py-2 rounded ${
                        isConnected
                            ? 'bg-blue-500 hover:bg-blue-600 text-white'
                            : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                    }`}
                >
                    {isConnected ? 'Start Agent' : 'Connecting...'}
                </button>
            </div>
        </div>
    );
};

export default Threads; 