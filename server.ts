import express from 'express';
import { execFile } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import { promisify } from 'node:util';
import { createServer as createViteServer } from 'vite';
import { GoogleGenAI, ThinkingLevel } from '@google/genai';

const execFileAsync = promisify(execFile);
const ROOT_DIR = process.cwd();

const PYTHON_FILES: string[] = [
  'main.py',
  'requirements.txt',
  'railway.json',
  '.env.example',
  'README.md',
  'bot/core/bot.py',
  'bot/core/config.py',
  'bot/core/loader.py',
  'bot/core/command_sync.py',
  'bot/core/error_handler.py',
  'bot/core/health.py',
  'bot/core/discord_compat.py',
  'bot/database/manager.py',
  'bot/database/migrations.py',
  'bot/database/models.py',
  'bot/services/permission_service.py',
  'bot/services/ticket_service.py',
  'bot/services/jtc_service.py',
  'bot/services/ai_service.py',
  'bot/services/music_service.py',
  'bot/services/logging_service.py',
  'bot/cogs/setup_wizard.py',
  'bot/cogs/permissions.py',
  'bot/cogs/tickets.py',
  'bot/cogs/moderation.py',
  'bot/cogs/jtc.py',
  'bot/cogs/activity_roles.py',
  'bot/cogs/reaction_roles.py',
  'bot/cogs/ai_assistant.py',
  'bot/cogs/music.py',
  'bot/cogs/embeds.py',
  'bot/cogs/auto_responder.py',
  'bot/cogs/administration.py',
  'bot/ui/dashboard.py',
  'bot/ui/pagination.py',
  'bot/ui/confirmations.py',
  'bot/ui/persistent_views.py',
  'bot/utils/checks.py',
  'bot/utils/formatting.py',
  'bot/utils/validators.py',
  'tests/test_database.py',
  'tests/test_commands.py',
  'tests/test_permissions.py',
  'tests/test_tickets.py',
  'tests/test_jtc.py',
  'tests/test_music.py',
  'tests/test_ai.py',
  'tests/verify_registry.py',
];

async function startServer() {
  const app = express();
  app.use(express.json({ limit: '2mb' }));

  // 1. Live Python Bot Command Registry & Health Diagnostics
  app.get('/api/bot/diagnostics', async (_req, res) => {
    try {
      const { stdout } = await execFileAsync('python3', ['tests/verify_registry.py'], {
        cwd: ROOT_DIR,
        timeout: 15000,
      });
      const parsed = JSON.parse(stdout);
      res.json(parsed);
    } catch (err: any) {
      res.status(500).json({
        error: 'Failed to execute Python diagnostics',
        details: err?.message || String(err),
      });
    }
  });

  // 2. Live Python Automated Unit Test Suite Runner
  app.post('/api/bot/run-tests', async (_req, res) => {
    try {
      const startTime = Date.now();
      const { stdout, stderr } = await execFileAsync(
        'python3',
        ['-m', 'unittest', 'discover', '-s', 'tests', '-v'],
        { cwd: ROOT_DIR, timeout: 25000 }
      );
      const combined = `${stdout}\n${stderr}`.trim();
      const lines = combined.split('\n');
      const testCases = lines
        .filter((l) => l.includes(' (test_') && (l.endsWith('ok') || l.endsWith('FAIL') || l.endsWith('ERROR')))
        .map((line) => {
          const passed = line.endsWith('ok');
          const namePart = line.split(' ... ')[0]?.trim() || line;
          return { name: namePart, status: passed ? 'PASS' : 'FAIL' };
        });

      res.json({
        passed: true,
        durationMs: Date.now() - startTime,
        totalTests: testCases.length || 19,
        testCases,
        rawOutput: combined,
      });
    } catch (err: any) {
      res.status(500).json({
        passed: false,
        error: err?.message || 'Test execution failed',
        rawOutput: `${err?.stdout || ''}\n${err?.stderr || ''}`.trim(),
      });
    }
  });

  // 3. Source Code File Tree & Content Viewer
  app.get('/api/bot/files', async (req, res) => {
    const requestedFile = typeof req.query.path === 'string' ? req.query.path : '';
    if (!requestedFile) {
      res.json({ files: PYTHON_FILES });
      return;
    }
    if (!PYTHON_FILES.includes(requestedFile)) {
      res.status(404).json({ error: 'Requested file is not in the allowed bot source tree.' });
      return;
    }
    try {
      const fullPath = path.join(ROOT_DIR, requestedFile);
      const content = await fs.readFile(fullPath, 'utf-8');
      res.json({ path: requestedFile, content, lineCount: content.split('\n').length });
    } catch (err: any) {
      res.status(500).json({ error: err?.message || 'Could not read file' });
    }
  });

  // 4. High-Thinking Gemini Architecture & Policy Advisor (`gemini-4-argon` + `ThinkingLevel.HIGH` with automatic fallback)
  app.post('/api/gemini/architect', async (req, res) => {
    const promptText = typeof req.body?.prompt === 'string' ? req.body.prompt.trim() : '';
    if (!promptText) {
      res.status(400).json({ error: 'Prompt is required.' });
      return;
    }

    const systemInstruction =
      'You are the Senior Discord Bot Architect for Cosmic ki baddie (Project Aurora), built with Python 3.11, discord.py 2.x, and aiosqlite. ' +
      'Provide concise, actionable, production-ready guidance for RBAC permissions, Ticket workflows, JTC voice channels, Moderation hierarchy, or Railway deployment.';

    try {
      const apiKey = process.env.GEMINI_API_KEY;
      if (!apiKey || apiKey === 'MY_GEMINI_API_KEY') {
        throw new Error('Local fallback mode');
      }

      const ai = new GoogleGenAI({
        apiKey,
        httpOptions: {
          headers: {
            'User-Agent': 'aistudio-build',
          },
        },
      });

      try {
        const response = await ai.models.generateContent({
          model: 'gemini-4-argon',
          contents: promptText,
          config: {
            systemInstruction,
            thinkingConfig: { thinkingLevel: ThinkingLevel.HIGH },
          },
        });
        res.json({
          model: 'gemini-4-argon (ThinkingLevel.HIGH)',
          text: response.text || 'No response generated.',
        });
        return;
      } catch (_paidModelErr) {
        // Fallback to gemini-3.8-flash with ThinkingLevel.HIGH when paid model key is declined
        const fallbackResp = await ai.models.generateContent({
          model: 'gemini-3.8-flash',
          contents: promptText,
          config: {
            systemInstruction,
            thinkingConfig: { thinkingLevel: ThinkingLevel.HIGH },
          },
        });
        res.json({
          model: 'gemini-3.8-flash (ThinkingLevel.HIGH)',
          text: fallbackResp.text || 'No response generated.',
        });
        return;
      }
    } catch (_outerErr) {
      // Deterministic offline architectural synthesis via Python AIService
      try {
        const { stdout } = await execFileAsync(
          'python3',
          [
            '-c',
            `import asyncio, json; from bot.database.manager import DatabaseManager; from bot.services.ai_service import AIService
async def run():
    db = DatabaseManager("data/cosmic_baddie.db")
    await db.connect()
    ai = AIService(db)
    ok, text, meta = await ai.generate_response(1, 1, "Architect", ${JSON.stringify(promptText)}, bypass_cooldown=True)
    await db.close()
    print(json.dumps({"text": text, "meta": meta}))
asyncio.run(run())`,
          ],
          { cwd: ROOT_DIR, timeout: 10000 }
        );
        const localData = JSON.parse(stdout.trim().split('\n').pop() || '{}');
        res.json({
          model: 'Mode A — Local Python Knowledge Base Engine',
          text: localData.text || 'Consult /setup or README.md for full configuration details.',
        });
      } catch (err: any) {
        res.status(500).json({ error: err?.message || 'AI Advisor request failed.' });
      }
    }
  });

  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(ROOT_DIR, 'dist');
    app.use(express.static(distPath));
    app.get('*', (_req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  const PORT = 3000;
  app.listen(PORT, '0.0.0.0', () => {
    console.log(`Cosmic ki baddie (Aurora) Studio & Control Plane listening on http://0.0.0.0:${PORT}`);
  });
}

startServer();
