import asyncio
import json
import os
import re
import requests
from playwright.async_api import async_playwright

# --- URLs ---
MOOV_ADIDAS_URL = "https://www.moov.com.ar/hombre?cgid=hombre&prefn1=brand&prefv1=adidas&srule=newest-products&start=0&sz=36"
MOOV_NIKE_URL = "https://www.moov.com.ar/hombre?cgid=hombre&prefn1=brand&prefv1=Nike&srule=newest-products&start=0&sz=36"
MOOV_ON_URL = "https://www.moov.com.ar/marcas?cgid=marcas&prefn1=brand&prefv1=On%20Running&srule=newest-products&start=0&sz=36"
DEXTER_ADIDAS_URL = "https://www.dexter.com.ar/hombre?cgid=hombre&prefn1=brand&prefv1=adidas&srule=newest-products&start=0&sz=36"
DEXTER_NIKE_URL = "https://www.dexter.com.ar/hombre/nike?srule=newest-products&start=0&sz=36"
DEXTER_ON_URL = "https://www.dexter.com.ar/hombre?cgid=hombre&prefn1=brand&prefv1=On%20Running&srule=newest-products&start=0&sz=36"
CRISTOBAL_URL = "https://www.cristobalcolon.com/categoria-producto/hombre/remeras-musculosas/?marca=adidas"
ZEUS_ADIDAS_URL = "https://www.zeus-shoes.com/hombre.html?genero=Hombre&manufacturer=Adidas&product_list_order=mst_f2&product_list_limit=24"
ZEUS_NIKE_URL = "https://www.zeus-shoes.com/hombre.html?genero=Hombre&manufacturer=Nike&product_list_order=mst_f2&product_list_limit=24"

# --- Snapshots ---
MOOV_ADIDAS_SNAPSHOT = "moov/snapshot_adidas.json"
MOOV_NIKE_SNAPSHOT = "moov/snapshot_nike.json"
MOOV_ON_SNAPSHOT = "moov/snapshot_on.json"
DEXTER_ADIDAS_SNAPSHOT = "dexter/snapshot_adidas.json"
DEXTER_NIKE_SNAPSHOT = "dexter/snapshot_nike.json"
DEXTER_ON_SNAPSHOT = "dexter/snapshot_on.json"
CRISTOBAL_SNAPSHOT = "cristobal/snapshot.json"
ZEUS_ADIDAS_SNAPSHOT = "zeus/snapshot_adidas.json"
ZEUS_NIKE_SNAPSHOT = "zeus/snapshot_nike.json"

# --- Moov (Playwright) ---
JS_EXTRACT = """
() => {
    const results = [];
    const gtmInputs = document.querySelectorAll('.productGtmData');
    gtmInputs.forEach((input) => {
        try {
            const data = JSON.parse(input.value);
            const item = data[0];
            const tile = input.closest('.product');
            let url = "";
            if (tile) {
                const allLinks = tile.querySelectorAll('a[href]');
                for (const link of allLinks) {
                    if (link.href && (link.href.includes('moov.com.ar') || link.href.includes('dexter.com.ar')) && !link.href.includes('#')) {
                        url = link.href;
                        break;
                    }
                }
            }
            results.push({
                id: item.item_id || item.id || "",
                name: item.item_name || item.name || "",
                brand: item.item_brand || item.brand || "",
                category: item.item_category || item.category || "",
                price: item.price || "",
                url: url
            });
        } catch(e) {}
    });
    return results;
}
"""

async def get_moov_products_from(url, label="Moov"):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        print(f"[{label}] Cargando pagina...")
        await page.goto(url, wait_until='networkidle', timeout=60000)
        try:
            await page.wait_for_selector('.productGtmData', state='attached', timeout=15000)
        except:
            print(f"[{label}] Advertencia: tardo en cargar, intentando igual...")
        products = await page.evaluate(JS_EXTRACT)
        await browser.close()
        return products

# --- Cristobal Colon (Playwright) ---
async def get_cristobal_products():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        print("[Cristobal] Cargando pagina...")
        await page.goto(CRISTOBAL_URL, wait_until='networkidle', timeout=60000)

        html = await page.content()
        await browser.close()

        ids = re.findall(r'post-(\d+)\s+product\s+type-', html)
        names = re.findall(r'woocommerce-loop-product__title[^>]*>(.*?)</h2>', html, re.DOTALL)
        urls = re.findall(r'woocommerce-LoopProduct-link[^"]*"[^"]*href="([^"]+)"', html)
        prices_raw = re.findall(r'woocommerce-Price-amount amount">[^<]*<bdi>(.*?)</bdi>', html)

        products = []
        for i in range(min(len(ids), len(names), len(urls))):
            price_clean = re.sub(r'<[^>]+>|&[^;]+;|\s', '', prices_raw[i]) if i < len(prices_raw) else ""
            products.append({
                "id": ids[i],
                "name": names[i].strip(),
                "price": price_clean,
                "url": urls[i]
            })

        return products

# --- Zeus (Playwright) ---
JS_EXTRACT_ZEUS = """
() => {
    const results = [];
    const items = document.querySelectorAll('li.product-item .product-item-info');
    items.forEach((info) => {
        try {
            const id = (info.id || "").replace('product-item-info_', '');
            const linkEl = info.querySelector('.product-item-link');
            const name = linkEl ? linkEl.textContent.trim() : "";
            const url = linkEl ? linkEl.href : "";
            const priceEl = info.querySelector('[data-price-type="finalPrice"]') || info.querySelector('[data-price-amount]');
            const price = priceEl ? priceEl.getAttribute('data-price-amount') : "";
            if (id && name) {
                results.push({ id, name, price, url });
            }
        } catch(e) {}
    });
    return results;
}
"""

async def load_zeus_page(page, url, label):
    last_error = None
    for attempt in range(3):
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            await page.wait_for_selector('.product-item-info', state='attached', timeout=15000)
            return
        except Exception as e:
            last_error = e
            print(f"[{label}] Intento {attempt + 1} fallo: {e}")
            await page.wait_for_timeout(2000)
    raise last_error

async def get_zeus_products(base_url, label="Zeus"):
    all_products = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        page_num = 1
        total_pages = 1
        try:
            while page_num <= total_pages:
                url = f"{base_url}&p={page_num}"
                print(f"[{label}] Cargando pagina {page_num}...")
                if page_num > 1:
                    await page.wait_for_timeout(1500)
                await load_zeus_page(page, url, label)
                if page_num == 1:
                    try:
                        amounts = await page.locator('#toolbar-amount .toolbar-number').all_text_contents()
                        total_count = int(re.sub(r'[^\d]', '', amounts[2]))
                        total_pages = max(1, -(-total_count // 24))
                    except Exception:
                        print(f"[{label}] Advertencia: no se pudo leer la paginacion, se toma solo la pagina 1.")
                products = await page.evaluate(JS_EXTRACT_ZEUS)
                for prod in products:
                    all_products[prod['id']] = prod
                page_num += 1
        except Exception as e:
            print(f"[{label}] ERROR: {e}")
            await browser.close()
            return None
        await browser.close()
        return list(all_products.values())

# --- Telegram ---
def send_telegram(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    # Dividir por lineas completas para no romper tags HTML
    lines = message.split('\n')
    chunks = []
    current = ""
    for line in lines:
        if len(current) + len(line) + 1 > 4000:
            if current:
                chunks.append(current)
            current = line
        else:
            current = current + '\n' + line if current else line
    if current:
        chunks.append(current)
    for chunk in chunks:
        response = requests.post(url, json={"chat_id": chat_id, "text": chunk, "parse_mode": "HTML", "disable_web_page_preview": True})
        print(f"Telegram response: {response.status_code} - {response.text[:100]}")

def format_price(price):
    try:
        num = re.sub(r'[^\d]', '', str(price))
        if num:
            return f"${int(num):,}".replace(',', '.')
        return str(price)
    except:
        return str(price)

# --- Comparar y notificar ---
def check_new(products, snapshot_file, store_name):
    if os.path.exists(snapshot_file):
        with open(snapshot_file) as f:
            previous = json.load(f)
        previous_ids = {p['id'] for p in previous if p.get('id')}
        print(f"[{store_name}] Snapshot anterior: {len(previous_ids)} productos")
    else:
        previous_ids = set()
        print(f"[{store_name}] Primera ejecucion: guardando snapshot inicial.")

    new_products = [p for p in products if p.get('id') and p['id'] not in previous_ids]

    os.makedirs(os.path.dirname(snapshot_file), exist_ok=True)
    with open(snapshot_file, 'w') as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    print(f"[{store_name}] Snapshot guardado.")

    return new_products

def format_brand_section(new_products, emoji, brand_name):
    if not new_products:
        return []
    lines = [f"\n{emoji} <b>{brand_name}</b>"]
    for p in new_products:
        name = p['name'].replace(' Hombre', '').replace(' hombre', '')
        price = format_price(p['price'])
        if p.get('url'):
            lines.append(f"• <a href=\"{p['url']}\">{name}</a> — {price}")
        else:
            lines.append(f"• {name} — {price}")
    return lines

async def scrape_and_check(url, snapshot, label):
    products = await get_moov_products_from(url, label)
    print(f"[{label}] Productos obtenidos: {len(products)}")
    if products:
        new = check_new(products, snapshot, label)
        if new:
            print(f"[{label}] {len(new)} productos nuevos")
        else:
            print(f"[{label}] Sin productos nuevos.")
        return new
    return []

# --- Main ---
async def main():
    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    # --- Moov ---
    new_moov_adidas = await scrape_and_check(MOOV_ADIDAS_URL, MOOV_ADIDAS_SNAPSHOT, "Moov Adidas")
    new_moov_nike = await scrape_and_check(MOOV_NIKE_URL, MOOV_NIKE_SNAPSHOT, "Moov Nike")
    new_moov_on = await scrape_and_check(MOOV_ON_URL, MOOV_ON_SNAPSHOT, "Moov On")

    total_moov = len(new_moov_adidas) + len(new_moov_nike) + len(new_moov_on)
    if total_moov > 0:
        lines = [f"🛍 <b>Moov — {total_moov} novedades</b>"]
        lines += format_brand_section(new_moov_adidas, "🟡", "Adidas")
        lines += format_brand_section(new_moov_nike, "🔵", "Nike")
        lines += format_brand_section(new_moov_on, "☁️", "On Running")
        send_telegram(token, chat_id, "\n".join(lines))

    # --- Dexter ---
    new_dex_adidas = await scrape_and_check(DEXTER_ADIDAS_URL, DEXTER_ADIDAS_SNAPSHOT, "Dexter Adidas")
    new_dex_nike = await scrape_and_check(DEXTER_NIKE_URL, DEXTER_NIKE_SNAPSHOT, "Dexter Nike")
    new_dex_on = await scrape_and_check(DEXTER_ON_URL, DEXTER_ON_SNAPSHOT, "Dexter On")

    total_dexter = len(new_dex_adidas) + len(new_dex_nike) + len(new_dex_on)
    if total_dexter > 0:
        lines = [f"👟 <b>Dexter — {total_dexter} novedades</b>"]
        lines += format_brand_section(new_dex_adidas, "🟡", "Adidas")
        lines += format_brand_section(new_dex_nike, "🔵", "Nike")
        lines += format_brand_section(new_dex_on, "☁️", "On Running")
        send_telegram(token, chat_id, "\n".join(lines))

    # --- Cristobal Colon ---
    cristobal_products = await get_cristobal_products()
    print(f"[Cristobal] Productos obtenidos: {len(cristobal_products)}")
    if cristobal_products:
        new_cristobal = check_new(cristobal_products, CRISTOBAL_SNAPSHOT, "Cristobal")
        if new_cristobal:
            print(f"[Cristobal] {len(new_cristobal)} productos nuevos")
            lines = [f"🛹 <b>Cristobal Colon — {len(new_cristobal)} novedades</b>\n"]
            for p in new_cristobal:
                price = format_price(p['price'])
                if p.get('url'):
                    lines.append(f"• <a href=\"{p['url']}\">{p['name']}</a> — {price}")
                else:
                    lines.append(f"• {p['name']} — {price}")
            send_telegram(token, chat_id, "\n".join(lines))
        else:
            print("[Cristobal] Sin productos nuevos.")

    # --- Zeus ---
    zeus_adidas_products = await get_zeus_products(ZEUS_ADIDAS_URL, "Zeus Adidas")
    print(f"[Zeus Adidas] Productos obtenidos: {len(zeus_adidas_products) if zeus_adidas_products else 0}")
    new_zeus_adidas = check_new(zeus_adidas_products, ZEUS_ADIDAS_SNAPSHOT, "Zeus Adidas") if zeus_adidas_products else []

    zeus_nike_products = await get_zeus_products(ZEUS_NIKE_URL, "Zeus Nike")
    print(f"[Zeus Nike] Productos obtenidos: {len(zeus_nike_products) if zeus_nike_products else 0}")
    new_zeus_nike = check_new(zeus_nike_products, ZEUS_NIKE_SNAPSHOT, "Zeus Nike") if zeus_nike_products else []

    total_zeus = len(new_zeus_adidas) + len(new_zeus_nike)
    if total_zeus > 0:
        lines = [f"⚡ <b>Zeus — {total_zeus} novedades</b>"]
        lines += format_brand_section(new_zeus_adidas, "🟡", "Adidas")
        lines += format_brand_section(new_zeus_nike, "🔵", "Nike")
        send_telegram(token, chat_id, "\n".join(lines))
    else:
        print("[Zeus] Sin productos nuevos.")

asyncio.run(main())
