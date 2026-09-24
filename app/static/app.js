// TrendAnalys arayüzü: cümleyi API'ye gönderir, sonuçları kartlara basar.

const form = document.getElementById("search-form");
const input = document.getElementById("query");
const button = document.getElementById("submit-button");
const results = document.getElementById("results");
const reading = document.getElementById("reading");
const tokens = document.getElementById("tokens");
const status = document.getElementById("status");
const cardTemplate = document.getElementById("card-template");

// Sıcaklık bandına göre vurgu rengi: soğukta mavi, serinde yeşil, sıcakta kehribar
const ACCENTS = [
  { max: 5, color: "#2f6ab8" },
  { max: 12, color: "#3a86a8" },
  { max: 18, color: "#2e8b74" },
  { max: 25, color: "#b8862f" },
  { max: Infinity, color: "#c4562f" },
];

function setAccent(temperature) {
  if (temperature === null || temperature === undefined) return;
  const band = ACCENTS.find((item) => temperature < item.max);
  document.documentElement.style.setProperty("--accent", band.color);
  document.documentElement.style.setProperty("--accent-soft", band.color + "1f");
}

function formatPrice(price, currency) {
  if (price === null) return "";
  const amount = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 0 }).format(price);
  return `${amount} ${currency === "TRY" ? "TL" : currency || ""}`.trim();
}

function showStatus(message) {
  status.textContent = message;
  status.hidden = false;
}

function renderTokens(data) {
  const items = [];
  const filters = data.filters;

  if (data.city) {
    const degrees = data.temperature === null ? "" : ` · ${Math.round(data.temperature)}°`;
    items.push(["hava", `${data.city}${degrees} · ${data.weather || "bilinmiyor"}`]);
  }
  if (filters.max_price && filters.min_price) {
    items.push(["bütçe", `${filters.min_price}–${filters.max_price} TL`]);
  } else if (filters.max_price) {
    items.push(["bütçe", `${filters.max_price} TL altı`]);
  } else if (filters.min_price) {
    items.push(["bütçe", `${filters.min_price} TL üzeri`]);
  }
  if (filters.category) items.push(["kategori", filters.category]);
  if (filters.color) items.push(["renk", filters.color]);
  if (filters.gender) items.push(["kime", filters.gender]);
  items.push(["modele giden", filters.text || data.query]);

  tokens.replaceChildren(
    ...items.map(([label, value], index) => {
      const token = document.createElement("div");
      token.className = "token";
      token.style.animationDelay = `${index * 45}ms`;
      token.innerHTML = `<span class="token-label"></span><span class="token-value"></span>`;
      token.querySelector(".token-label").textContent = label;
      token.querySelector(".token-value").textContent = value;
      return token;
    })
  );
  reading.hidden = false;
}

function renderCard(product) {
  const card = cardTemplate.content.cloneNode(true);
  const image = card.querySelector("img");
  const imageLink = card.querySelector(".card-image");

  if (product.image_url) {
    image.src = product.image_url;
    image.alt = product.name;
  } else {
    image.remove();
  }
  imageLink.href = product.url || "#";

  card.querySelector(".card-brand").textContent = product.brand || "";
  card.querySelector(".card-name").textContent = product.name;

  const price = card.querySelector(".card-price");
  price.textContent = formatPrice(product.price, product.currency);
  if (product.rating) {
    const rating = document.createElement("span");
    rating.className = "rating";
    rating.textContent = `★ ${product.rating.toFixed(1)}`;
    price.appendChild(rating);
  }

  card.querySelector(".card-why").textContent = product.why || "";
  card.querySelector(".card-link").href = product.url || "#";
  return card;
}

function showSkeletons(count = 8) {
  results.replaceChildren(
    ...Array.from({ length: count }, () => {
      const box = document.createElement("div");
      box.className = "skeleton";
      return box;
    })
  );
}

async function runSearch(query) {
  status.hidden = true;
  button.disabled = true;
  showSkeletons();

  try {
    const response = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, limit: 12 }),
    });

    if (!response.ok) {
      throw new Error(response.status === 422 ? "Cümle en az 2 karakter olmalı." : "Arama yapılamadı.");
    }

    const data = await response.json();
    setAccent(data.temperature);
    renderTokens(data);

    if (data.results.length === 0) {
      results.replaceChildren();
      showStatus(data.message || "Bu cümleye uyan ürün bulunamadı. Daha genel bir cümle deneyebilirsin.");
      return;
    }

    results.replaceChildren(...data.results.map(renderCard));
  } catch (error) {
    results.replaceChildren();
    showStatus(`${error.message} Sunucu çalışıyor mu kontrol et.`);
  } finally {
    button.disabled = false;
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = input.value.trim();
  if (query.length >= 2) runSearch(query);
});

// Enter arar, Shift+Enter alt satıra geçer
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

document.getElementById("examples").addEventListener("click", (event) => {
  const chip = event.target.closest(".chip");
  if (!chip) return;
  input.value = chip.textContent;
  runSearch(chip.textContent);
});
