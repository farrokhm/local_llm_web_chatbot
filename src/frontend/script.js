const chatBox = document.getElementById("chat");
const input = document.getElementById("message");
const modelSelect = document.getElementById("model-select");
const temperatureSlider = document.getElementById("temperature-slider");
const temperatureValue = document.getElementById("temperature-value");
const streamCheckbox = document.getElementById("stream-checkbox");

// Update the temperature display when the slider is moved
temperatureSlider.addEventListener("input", () => {
  temperatureValue.textContent = temperatureSlider.value;
});

async function sendMessage() {
  const message = input.value.trim();
  if (!message) return;

  chatBox.innerHTML += `🧑‍💻 You: ${message}\n`;
  input.value = "";

  const model = modelSelect.value;
  const temperature = parseFloat(temperatureSlider.value);
  const stream = streamCheckbox.checked;

  try {
    const response = await fetch("http://localhost:8000/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: message,
        model: model,
        temperature: temperature,
        stream: stream,
      }),
    });

    if (stream) {
      // Handle streaming response
      chatBox.innerHTML += `🤖 AI: `;
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          chatBox.innerHTML += `\n\n`;
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        
        for (let i = 0; i < lines.length - 1; i++) {
          const line = lines[i];
          if (line.trim() === "") continue;
          try {
            const parsed = JSON.parse(line);
            if (parsed.message && parsed.message.content) {
                chatBox.innerHTML += parsed.message.content;
                chatBox.scrollTop = chatBox.scrollHeight;
            }
          } catch (e) {
            console.error("Error parsing stream chunk:", line, e);
          }
        }
        buffer = lines[lines.length - 1];
      }
    } else {
      // Handle non-streaming response
      const data = await response.json();
      if (data.response) {
        chatBox.innerHTML += `🤖 AI: ${data.response}\n\n`;
      } else {
        chatBox.innerHTML += `⚠️ Error: ${data.error || "Unknown error"}\n\n`;
      }
    }
  } catch (error) {
    chatBox.innerHTML += `❌ Network Error: ${error.message}\n\n`;
  }
  chatBox.scrollTop = chatBox.scrollHeight;
}

async function resetChat() {
  try {
    await fetch("http://localhost:8000/api/reset", { method: "POST" });
    chatBox.innerHTML += `🧹 Chat history cleared.\n\n`;
  } catch (error) {
    chatBox.innerHTML += `❌ Reset failed: ${error.message}\n\n`;
  }
}
