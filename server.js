import express from "express";
import cors from "cors";

const app = express();
app.use(cors());

async function expandUrl(inputUrl) {
  if (!/^https?:\/\//i.test(inputUrl)) {
    throw new Error("Invalid URL: must start with http:// or https://");
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);

  try {
    const res = await fetch(inputUrl, {
      method: "GET",
      redirect: "follow",
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.7"
      },
      signal: controller.signal
    });

    return {
      ok: true,
      status: res.status,
      expandedUrl: res.url
    };
  } catch (err) {
    return {
      ok: false,
      error: err.name === "AbortError" ? "Request timed out" : String(err)
    };
  } finally {
    clearTimeout(timeout);
  }
}

app.get("/expand", async (req, res) => {
  const { url } = req.query;

  if (!url) {
    return res.status(400).json({ ok: false, error: "Missing ?url=" });
  }

  try {
    const result = await expandUrl(url);
    if (result.ok) {
      return res.json({
        ok: true,
        input: url,
        expandedUrl: result.expandedUrl,
        status: result.status
      });
    } else {
      return res.status(502).json({ ok: false, error: result.error });
    }
  } catch (e) {
    return res.status(500).json({ ok: false, error: String(e) });
  }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`URL Expander running on port ${PORT}`);
});
