let ws;

let audioRecorder;
let audioPlayer;

function appendContent(text) {
  const messages = document.getElementById("messages");
  const message = document.createElement("li");
  const content = document.createTextNode(text);
  message.appendChild(content);
  messages.appendChild(message);
}

function makeNewTextBlock(text = "") {
  let newElement = document.createElement("p");
  newElement.textContent = text;
  formReceivedTextContainer.appendChild(newElement);
}

function appendToTextBlock(text) {
  let textElements = formReceivedTextContainer.children;
  if (textElements.length == 0) {
    makeNewTextBlock();
  }
  textElements[textElements.length - 1].textContent += text;
}

function initWs() {
  const client_id = Date.now();
  document.querySelector("#ws-id").textContent = client_id;
  ws = new WebSocket(`ws://localhost:8000/realtime/${client_id}`);

  ws.onopen = function (event) {
    appendContent("Connected to server");
  };

  audioPlayer = new Player();
  audioPlayer.init(24000);

  ws.onmessage = function (event) {
    const message = JSON.parse(event.data);

    let consoleLog = "" + message.type;

    switch (message.type) {
      case "response.function_call_arguments.done":
        handleFunctionCall(message);
        break;
      case "session.created":
        setFormInputState(InputState.ReadyToStop);
        makeNewTextBlock("<< Session Started >>");
        makeNewTextBlock();
        break;
      case "response.audio_transcript.delta":
        appendToTextBlock(message.delta);
        break;
      case "response.audio.delta":
        const binary = atob(message.delta);
        const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
        const pcmData = new Int16Array(bytes.buffer);
        audioPlayer.play(pcmData);
        break;

      case "input_audio_buffer.speech_started":
        makeNewTextBlock("<< Speech Started >>");
        if (enableAzureSpeech) {
          makeNewTextBlock("<< Azure Speech Started >>");
          let textElements = formReceivedTextContainer.children;
          latestInputSpeechBlock = textElements[textElements.length - 2];
          latestInputAzureSpeechBlock = textElements[textElements.length - 1];
        } else {
          let textElements = formReceivedTextContainer.children;
          latestInputSpeechBlock = textElements[textElements.length - 1];
        }
        makeNewTextBlock();
        audioPlayer.clear();
        break;
      case "conversation.item.input_audio_transcription.completed":
        latestInputSpeechBlock.textContent += " User: " + message.transcript;
        break;
      case "response.done":
        formReceivedTextContainer.appendChild(document.createElement("hr"));
        break;
      default:
        consoleLog = JSON.stringify(message, null, 2);
        break;
    }
    if (consoleLog) {
      console.log(consoleLog);
    }
  };

  ws.onclose = function (event) {
    appendContent("Disconnected from server");
  };

  ws.onerror = function (error) {
    appendContent(error.message);
  };
}

let recordingActive = false;
let buffer = new Uint8Array();

function combineArray(newData) {
  const newBuffer = new Uint8Array(buffer.length + newData.length);
  newBuffer.set(buffer);
  newBuffer.set(newData, buffer.length);
  buffer = newBuffer;
}

function processAudioRecordingBuffer(data) {
  const uint8Array = new Uint8Array(data);
  combineArray(uint8Array);
  if (buffer.length >= 4800) {
    const toSend = new Uint8Array(buffer.slice(0, 4800));
    buffer = new Uint8Array(buffer.slice(4800));
    const regularArray = String.fromCharCode(...toSend);
    const base64 = btoa(regularArray);
    if (recordingActive) {
      realtimeStreaming.send({
        type: "input_audio_buffer.append",
        audio: base64,
      });
    }
  }
}

async function resetAudio(startRecording) {
  recordingActive = false;
  if (audioRecorder) {
    audioRecorder.stop();
  }

  if (audioPlayer) {
    audioPlayer.clear();
  }

  audioRecorder = new Recorder(processAudioRecordingBuffer);
  audioPlayer = new Player();
  audioPlayer.init(24000);

  if (startRecording) {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioRecorder.start(stream);
    recordingActive = true;
  }
}

async function start() {
  initWs();
  // resetAudio(true);
}

function send(event) {
  event.preventDefault();

  const input = document.querySelector("#message");
  ws.send(input.value);
  input.value = "";
}

function stop() {
  ws.close();
  resetAudio(false);
}
