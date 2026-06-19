import express, { Request, Response } from "express";
import path from "path";
import { createServer as createViteServer } from "vite";
import multer from "multer";
import axios from "axios";
import FormData from "form-data";

const upload = multer({ storage: multer.memoryStorage() });

async function startServer() {
  const app = express();
  const PORT = 3000;

  app.use(express.json({ limit: '50mb' }));
  app.use(express.urlencoded({ limit: '50mb', extended: true }));

  app.post("/api/upload", upload.single("file"), async (req: Request, res: Response) => {
    try {
      const customInstruction = req.body.instruction || "";
      const file = req.file;

      const formData = new FormData();

      if (customInstruction) {
        formData.append("extra_text", customInstruction);
      }

      if (file) {
        formData.append("file", file.buffer, {
          filename: file.originalname,
          contentType: file.mimetype,
        });
      }

      console.log("Sending request to Python AI Server...");

      const pythonResponse = await axios.post("http://127.0.0.1:8000/analyze", formData, {
        headers: {
          ...formData.getHeaders(),
        },
        maxContentLength: Infinity,
        maxBodyLength: Infinity,
      });

      const rawAiData = pythonResponse.data.data;

      let parsedJson;
      try {
        parsedJson = typeof rawAiData === "string" ? JSON.parse(rawAiData) : rawAiData;
      } catch (e) {
        parsedJson = rawAiData;
      }

      res.json({
        result: parsedJson,
        originalFileName: file ? file.originalname : "No file",
        mimeType: file ? file.mimetype : null,
        base64Data: file ? file.buffer.toString("base64") : null
      });

    } catch (error: any) {
      console.error("Upload API Error (Connecting to Python):", error.message);
      res.status(500).json({ error: "Failed to process document through Python AI Server" });
    }
  });

  app.post("/api/chat", async (req: Request, res: Response) => {
    try {
      const { message, chatHistory, base64Data, mimeType } = req.body;
      const systemInstruction = `You are NotebookLM, a helpful Knowledge Assistant...`;
      res.json({ reply: "Chat feature backend stub" });
    } catch (error: any) {
      res.status(500).json({ error: error.message });
    }
  });

  // Vite middleware for development
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (req: Request, res: Response) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`Server running on http://localhost:${PORT}`);
  });
}

startServer();
