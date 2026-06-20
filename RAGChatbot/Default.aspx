<asp:Content ID="BodyContent" ContentPlaceHolderID="MainContent" runat="server">

    <style>
        .chat-container {
            max-width: 800px;
            margin: 30px auto;
            font-family: Arial, sans-serif;
        }
        .url-row {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }
        .url-row input {
            flex: 1;
            padding: 10px;
            border: 1px solid #ccc;
            border-radius: 6px;
            font-size: 1em;
        }
        .url-row button {
            padding: 10px 20px;
            background: #28a745;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 1em;
        }
        .url-row button:hover { background: #218838; }
        .progress-container {
            display: none;
            margin-bottom: 20px;
        }
        .progress-label {
            font-size: 0.9em;
            color: #555;
            margin-bottom: 5px;
        }
        .progress-bar-outer {
            width: 100%;
            background: #e9ecef;
            border-radius: 8px;
            height: 22px;
            overflow: hidden;
        }
        .progress-bar-inner {
            height: 100%;
            background: #007bff;
            border-radius: 8px;
            width: 0%;
            transition: width 0.4s ease;
        }
        .chat-box {
            height: 400px;
            overflow-y: auto;
            border: 1px solid #ccc;
            border-radius: 8px;
            padding: 15px;
            background: #f9f9f9;
            margin-bottom: 15px;
            display: none;
        }
        .message {
            margin-bottom: 15px;
            padding: 10px 14px;
            border-radius: 8px;
            max-width: 80%;
            line-height: 1.5;
        }
        .user-message {
            background: #007bff;
            color: white;
            margin-left: auto;
            text-align: right;
        }
        .bot-message {
            background: #e9ecef;
            color: #333;
        }
        .sources {
            font-size: 0.75em;
            color: #666;
            margin-top: 5px;
        }
        .input-row {
            display: flex;
            gap: 10px;
            display: none;
        }
        .input-row input {
            flex: 1;
            padding: 10px;
            border: 1px solid #ccc;
            border-radius: 6px;
            font-size: 1em;
        }
        .input-row button {
            padding: 10px 20px;
            background: #007bff;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 1em;
        }
        .input-row button:hover { background: #0056b3; }
        .thinking {
            color: #999;
            font-style: italic;
        }
        .status-text {
            font-size: 0.85em;
            color: #666;
            margin-top: 6px;
        }
    </style>

    <div class="chat-container">
        <h2>RAG Chatbot</h2>
        <p>Enter any website URL to start chatting with it.</p>

        <!-- URL Input -->
        <div class="url-row">
            <input type="text" id="urlInput" placeholder="https://example.com" />
            <button type="button" onclick="loadWebsite()">Load Website</button>
        </div>

        <!-- Progress Bar -->
        <div class="progress-container" id="progressContainer">
            <div class="progress-label" id="progressLabel">Starting...</div>
            <div class="progress-bar-outer">
                <div class="progress-bar-inner" id="progressBar"></div>
            </div>
            <div class="status-text" id="statusText"></div>
        </div>

        <!-- Chat Box -->
        <div class="chat-box" id="chatBox">
            <div class="message bot-message">
                Hello! Ask me anything about the website.
            </div>
        </div>

        <!-- Message Input -->
        <div class="input-row" id="inputRow">
            <input type="text" id="questionInput" placeholder="Type your question..."
                   onkeypress="handleKey(event)" />
            <button type="button" onclick="sendMessage()">Send</button>
        </div>
    </div>

    <script>
        const API_URL = "http://localhost:5000";
        let progressInterval = null;

        function loadWebsite() {
            const url = document.getElementById("urlInput").value.trim();
            if (!url) { alert("Please enter a URL first."); return; }

            // Show progress bar, hide chat
            document.getElementById("progressContainer").style.display = "block";
            document.getElementById("chatBox").style.display = "none";
            document.getElementById("inputRow").style.display = "none";
            setProgress(0, "Starting pipeline...");

            fetch(API_URL + "/load", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url: url })
            }).then(() => {
                // Start polling progress
                progressInterval = setInterval(pollProgress, 1500);
            }).catch(() => {
                setProgress(0, "Error: Could not connect to API.");
            });
        }

        function pollProgress() {
            fetch(API_URL + "/progress")
                .then(r => r.json())
                .then(data => {
                    setProgress(data.percent, data.message);

                    if (data.status === "ready") {
                        clearInterval(progressInterval);
                        setTimeout(showChat, 800);
                    }
                    if (data.status === "error") {
                        clearInterval(progressInterval);
                        document.getElementById("progressLabel").innerText = "Error: " + data.message;
                    }
                });
        }

        function setProgress(percent, message) {
            document.getElementById("progressBar").style.width = percent + "%";
            document.getElementById("progressLabel").innerText = percent + "% — " + message;
        }

        function showChat() {
            document.getElementById("progressContainer").style.display = "none";
            document.getElementById("chatBox").style.display = "block";
            document.getElementById("inputRow").style.display = "flex";
        }

        function handleKey(event) {
            if (event.key === "Enter") sendMessage();
        }

        function addMessage(text, isUser, sources) {
            const chatBox = document.getElementById("chatBox");
            const div = document.createElement("div");
            div.className = "message " + (isUser ? "user-message" : "bot-message");
            div.innerText = text;
            if (sources && sources.length > 0) {
                const srcDiv = document.createElement("div");
                srcDiv.className = "sources";
                srcDiv.innerHTML = "Sources: " + sources.map(s =>
                    '<a href="' + s + '" target="_blank">' + s + '</a>'
                ).join(", ");
                div.appendChild(srcDiv);
            }
            chatBox.appendChild(div);
            chatBox.scrollTop = chatBox.scrollHeight;
        }

        function addThinking() {
            const chatBox = document.getElementById("chatBox");
            const div = document.createElement("div");
            div.className = "message bot-message thinking";
            div.id = "thinkingMsg";
            div.innerText = "Thinking...";
            chatBox.appendChild(div);
            chatBox.scrollTop = chatBox.scrollHeight;
        }

        function removeThinking() {
            const el = document.getElementById("thinkingMsg");
            if (el) el.remove();
        }

        async function sendMessage() {
            const input = document.getElementById("questionInput");
            const question = input.value.trim();
            if (!question) return;
            addMessage(question, true);
            input.value = "";
            addThinking();
            try {
                const response = await fetch(API_URL + "/chat", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ question: question })
                });
                const data = await response.json();
                removeThinking();
                addMessage(data.answer, false, data.sources);
            } catch (error) {
                removeThinking();
                addMessage("Error: Could not connect to API.", false);
            }
        }
    </script>

</asp:Content>