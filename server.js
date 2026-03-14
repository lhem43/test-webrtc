const express = require("express");
const http = require("http");
const path = require("path");
const WebSocket = require("ws");

const app = express();
const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

app.use(express.static(path.join(__dirname, "public")));

const rooms = new Map();
// rooms = Map<roomId, Set<ws>>

function send(ws, data) {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(data));
  }
}

wss.on("connection", (ws) => {
  ws.roomId = null;
  ws.role = null;

  ws.on("message", (message) => {
    let data;
    try {
      data = JSON.parse(message.toString());
    } catch (err) {
      console.error("Invalid JSON:", err);
      return;
    }

    if (data.type === "join") {
      const { roomId, role } = data;
      ws.roomId = roomId;
      ws.role = role;

      if (!rooms.has(roomId)) {
        rooms.set(roomId, new Set());
      }
      rooms.get(roomId).add(ws);

      console.log(`Client joined room=${roomId}, role=${role}`);
      send(ws, { type: "joined", roomId, role });
      return;
    }

    // Forward signaling messages to others in same room
    const roomId = ws.roomId;
    if (!roomId || !rooms.has(roomId)) return;

    for (const client of rooms.get(roomId)) {
      if (client !== ws) {
        send(client, data);
      }
    }
  });

  ws.on("close", () => {
    const roomId = ws.roomId;
    if (roomId && rooms.has(roomId)) {
      rooms.get(roomId).delete(ws);
      if (rooms.get(roomId).size === 0) {
        rooms.delete(roomId);
      }
    }
    console.log("Client disconnected");
  });
});

const PORT = process.env.PORT || 3000;
server.listen(PORT, "0.0.0.0", () => {
  console.log(`Server running on http://0.0.0.0:${PORT}`);
});