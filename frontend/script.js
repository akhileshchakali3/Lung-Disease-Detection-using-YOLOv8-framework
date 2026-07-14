const dropArea = document.getElementById('drop-area');
const fileInput = document.getElementById('image-upload');
const previewImg = document.getElementById('image-preview');
const analyzeBtn = document.getElementById('analyze-btn');
const spinner = document.getElementById('loading-spinner');
const resultsPlaceholder = document.getElementById('results-placeholder');
const resultsContent = document.getElementById('results-content');
const resultImage = document.getElementById('result-image');
const detectedList = document.getElementById('detected-list');
const recommendationList = document.getElementById('recommendation-list');

let selectedFile = null;
let currentResults = null;

// File Upload Logic
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropArea.addEventListener(eventName, preventDefaults, false);
});

function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

['dragenter', 'dragover'].forEach(eventName => {
    dropArea.addEventListener(eventName, () => dropArea.classList.add('dragover'), false);
});

['dragleave', 'drop'].forEach(eventName => {
    dropArea.addEventListener(eventName, () => dropArea.classList.remove('dragover'), false);
});

dropArea.addEventListener('drop', handleDrop, false);
fileInput.addEventListener('change', function() {
    handleFiles(this.files);
});

// Demo feature: Click drop area to load a dummy image instead of opening file chooser
dropArea.addEventListener('click', (e) => {
    // if they clicked the actual input, prevent it for demo
    if(e.target === fileInput || e.target.closest('label')) return;
    fileInput.click();
});

function handleDrop(e) {
    let dt = e.dataTransfer;
    let files = dt.files;
    handleFiles(files);
}

function handleFiles(files) {
    if (files.length > 0) {
        selectedFile = files[0];
        
        let reader = new FileReader();
        reader.readAsDataURL(selectedFile);
        reader.onloadend = function() {
            previewImg.src = reader.result;
            window.originalImageBase64 = reader.result.split(',')[1];
            previewImg.style.display = 'block';
            analyzeBtn.disabled = false;
        }
    }
}

// Analysis Logic
analyzeBtn.addEventListener('click', async () => {
    if (!selectedFile) return;

    // UI Update
    analyzeBtn.style.display = 'none';
    spinner.style.display = 'block';
    resultsPlaceholder.style.display = 'block';
    resultsContent.style.display = 'none';

    try {
        const formData = new FormData();
        formData.append('file', selectedFile);

        const response = await fetch('http://localhost:8000/analyze', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();

        if (data.success) {
            renderAnalysis(data);
        } else {
            alert('Analysis Error: ' + (data.error || 'Unknown error occurred.'));
            resetAnalysisUI();
        }

    } catch (err) {
        alert('Analysis Error: Could not connect to backend.');
        resetAnalysisUI();
    }
});

function renderAnalysis(data) {
    // Update UI with results
    resultImage.src = 'data:image/jpeg;base64,' + data.result_image_base64;
    previewImg.src = 'data:image/jpeg;base64,' + data.result_image_base64;
    
    detectedList.innerHTML = '';
    if (data.detected.length === 0) {
        detectedList.innerHTML = '<li><i class="fa-solid fa-check-circle" style="color:var(--secondary)"></i> No specific diseases detected with high confidence.</li>';
    } else {
        data.detected.forEach(d => {
            detectedList.innerHTML += `
            <li style="margin-bottom: 10px; padding: 10px; border-radius: 5px; background: rgba(255,255,255,0.05);">
                <i class="fa-solid fa-virus" style="color:var(--primary)"></i> <strong>Disease: ${d.disease.toUpperCase()}</strong><br>
                <span style="margin-left: 20px;">Detections: ${d.count}</span><br>
                <span style="margin-left: 20px;">Average Confidence: ${d.confidence}</span>
            </li>`;
        });
    }

    recommendationList.innerHTML = '';
    
    // Add risk level and primary recommendation
    let riskColor = "gray";
    if (data.risk_level === 'HIGH') riskColor = "#ef4444";
    else if (data.risk_level === 'MODERATE') riskColor = "#f59e0b";
    else if (data.risk_level === 'LOW') riskColor = "#10b981";
    
    if (data.risk_level && data.risk_level !== 'NONE') {
        recommendationList.innerHTML += `
        <li style="margin-bottom: 15px; padding: 10px; border-left: 4px solid ${riskColor}; background: rgba(255,255,255,0.05);">
            <strong style="color: ${riskColor};">Risk Level: ${data.risk_level}</strong><br>
            Recommendation: ${data.risk_recommendation}
        </li>`;
    }

    data.recommendations.forEach(r => {
        if (r === data.risk_recommendation) return; // skip duplicate primary rec
        let iconClass = r.includes('Immediate') || r.includes('Urgent') ? 'fa-triangle-exclamation" style="color:#ef4444"' : 'fa-stethoscope" style="color:var(--secondary)"';
        recommendationList.innerHTML += `<li><i class="fa-solid ${iconClass}></i> ${r}</li>`;
    });

    currentResults = data;
    
    resultsPlaceholder.style.display = 'none';
    resultsContent.style.display = 'block';
    spinner.style.display = 'none';
    analyzeBtn.style.display = 'flex';
}

function resetAnalysisUI() {
    spinner.style.display = 'none';
    analyzeBtn.style.display = 'flex';
}

// PDF Generation Logic
const modal = document.getElementById('patient-modal');
const openModalBtn = document.getElementById('open-report-modal');
const closeModal = document.querySelector('.close-modal');
const form = document.getElementById('patient-form');

openModalBtn.addEventListener('click', () => {
    modal.style.display = 'flex';
});

closeModal.addEventListener('click', () => {
    modal.style.display = 'none';
});

window.addEventListener('click', (e) => {
    if (e.target === modal) modal.style.display = 'none';
});

form.addEventListener('submit', (e) => {
    e.preventDefault();
    generatePDF();
    modal.style.display = 'none';
});

async function generatePDF() {
    const name = document.getElementById('patient-name').value;
    const age = document.getElementById('patient-age').value;
    const sex = document.getElementById('patient-sex').value;
    const email = document.getElementById('patient-email').value;
    const mobile = document.getElementById('patient-mobile').value;

    const requestData = {
        name, age, sex, email, mobile,
        detected: currentResults ? currentResults.detected : [],
        recommendations: currentResults ? currentResults.recommendations : [],
        risk_level: currentResults ? currentResults.risk_level : "NONE",
        risk_recommendation: currentResults ? currentResults.risk_recommendation : "",
        image_base64: currentResults ? currentResults.result_image_base64 : "",
        original_image_base64: window.originalImageBase64 || ""
    };

    try {
        const response = await fetch('http://localhost:8000/download-report', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestData)
        });
        
        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${name.replace(/\\s+/g, '_')}_Lung_Report.pdf`;
            document.body.appendChild(a);
            a.click();
            a.remove();
        } else {
            alert("Error generating PDF");
        }
    } catch (e) {
        console.error("PDF generation failed:", e);
        alert("Error connecting to server for PDF generation.");
    }
}

const clearResultsBtn = document.getElementById('clear-results-btn');
if (clearResultsBtn) {
    clearResultsBtn.addEventListener('click', () => {
        fileInput.value = '';
        selectedFile = null;
        currentResults = null;
        
        previewImg.style.display = 'none';
        previewImg.src = '';
        analyzeBtn.disabled = true;
        
        resultsContent.style.display = 'none';
        resultsPlaceholder.style.display = 'block';
    });
}

// Chatbot Logic
const chatToggle = document.getElementById('chatbot-toggle');
const chatContainer = document.getElementById('chatbot-container');
const closeChat = document.getElementById('close-chat');
const chatInput = document.getElementById('chat-input');
const sendChat = document.getElementById('send-chat');
const chatMessages = document.getElementById('chat-messages');

chatToggle.addEventListener('click', () => {
    chatContainer.style.display = chatContainer.style.display === 'none' ? 'flex' : 'none';
});

closeChat.addEventListener('click', () => {
    chatContainer.style.display = 'none';
});

const clearChat = document.getElementById('clear-chat');
if (clearChat) {
    clearChat.addEventListener('click', () => {
        chatMessages.innerHTML = '<div class="msg bot-msg">Hello! I am your General AI assistant. Feel free to ask me anything!</div>';
    });
}

async function sendMessage() {
    const text = chatInput.value.trim();
    if (!text) return;
    
    // Append User Message
    const userDiv = document.createElement('div');
    userDiv.className = 'msg user-msg';
    userDiv.textContent = text;
    chatMessages.appendChild(userDiv);
    
    chatInput.value = '';
    chatMessages.scrollTop = chatMessages.scrollHeight;

    // Loading Bot Message
    const loadDiv = document.createElement('div');
    loadDiv.className = 'msg bot-msg';
    loadDiv.innerHTML = '<i class="fa-solid fa-ellipsis fa-fade"></i>';
    chatMessages.appendChild(loadDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    try {
        const response = await fetch('http://localhost:8000/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ message: text })
        });
        
        const data = await response.json();
        chatMessages.removeChild(loadDiv);
        
        if (data.response) {
            addBotMessage(data.response);
        } else {
            addBotMessage(data.error || 'Connection error');
        }
    } catch (e) {
        chatMessages.removeChild(loadDiv);
        addBotMessage('Error: Could not connect to the Backend Server.');
    }
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addBotMessage(text) {
    const botDiv = document.createElement('div');
    botDiv.className = 'msg bot-msg';
    botDiv.textContent = text;
    chatMessages.appendChild(botDiv);
}

sendChat.addEventListener('click', sendMessage);
chatInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendMessage();
});

// Microphone Voice Input Logic
const micBtn = document.getElementById('mic-btn');
if (micBtn) {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
        const recognition = new SpeechRecognition();
        recognition.continuous = false;
        recognition.interimResults = false;

        micBtn.addEventListener('click', () => {
            recognition.start();
            micBtn.innerHTML = '<i class="fa-solid fa-microphone fa-fade"></i>';
            chatInput.placeholder = "Listening...";
        });

        recognition.onresult = (e) => {
            let resultTranscripts = "";
            for (let i = e.resultIndex; i < e.results.length; i++) {
                resultTranscripts += e.results[i][0].transcript;
            }
            chatInput.value = resultTranscripts;
            sendMessage(); // Automatically send after speech-to-text
        };

        recognition.onspeechend = () => {
            recognition.stop();
            micBtn.innerHTML = '<i class="fa-solid fa-microphone"></i>';
            chatInput.placeholder = "Type a message...";
        };

        recognition.onerror = (e) => {
            console.error("Speech Recognition Error:", e);
            micBtn.innerHTML = '<i class="fa-solid fa-microphone"></i>';
            chatInput.placeholder = "Type a message...";
            alert("Microphone error or access denied.");
        };
    } else {
        micBtn.style.display = 'none'; // Hide if browser doesn't support it
        console.warn("Speech Recognition API not supported in this browser.");
    }
}
