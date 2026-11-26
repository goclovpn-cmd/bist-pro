export default async function handler(req, res) {
  const { hisseler } = req.query;
  if (!hisseler) {
    return res.status(400).json({ error: "Hisse parametresi gerekli" });
  }

  const liste = hisseler
    .split(",")
    .map(h => h.trim().toUpperCase())
    .filter(Boolean)
    .slice(0, 50);

  const sonuc = {};

  // Yahoo Finance'e ani yük bindirmemek için 5'erli paketler halinde çek
  const paketBoyutu = 5;
  for (let i = 0; i < liste.length; i += paketBoyutu) {
    const paket = liste.slice(i, i + paketBoyutu);
    await Promise.all(
      paket.map(async (h) => {
        try {
          const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(h)}.IS?interval=1d&range=5d`;
          const r = await fetch(url, {
            headers: { "User-Agent": "Mozilla/5.0" }
          });
          if (!r.ok) return;
          const data = await r.json();
          const meta = data?.chart?.result?.[0]?.meta;
          const price = meta?.regularMarketPrice ?? meta?.chartPreviousClose;
          if (typeof price === "number" && !isNaN(price)) {
            sonuc[h] = Math.round(price * 100) / 100;
          }
        } catch (e) {}
      })
    );
  }

  // Vercel Edge Cache: 90 saniye boyunca tüm arkadaşların aynı sorguyu tek istekten paylaşır
  res.setHeader("Cache-Control", "s-maxage=90, stale-while-revalidate=30");
  return res.status(200).json(sonuc);
}
