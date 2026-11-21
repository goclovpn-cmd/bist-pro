module.exports = async (req, res) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  const raw = (req.query.hisseler || "").toString();
  const hisseler = raw.split(",").map(h => h.trim().toUpperCase()).filter(Boolean);

  if (!hisseler.length) {
    return res.status(400).json({ error: "Hisse belirtilmedi" });
  }

  const sonuc = {};
  const headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
  };

  await Promise.all(hisseler.map(async (h) => {
    const urls = [
      `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(h)}.IS?range=5d&interval=1d`,
      `https://query2.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(h)}.IS?range=5d&interval=1d`
    ];
    for (const url of urls) {
      try {
        const r = await fetch(url, { headers });
        if (!r.ok) continue;
        const data = await r.json();
        const meta = data?.chart?.result?.[0]?.meta;
        if (meta && typeof meta.regularMarketPrice === "number") {
          sonuc[h] = Math.round(meta.regularMarketPrice * 100) / 100;
          break;
        }
      } catch (e) {}
    }
  }));

  return res.status(200).json(sonuc);
};
