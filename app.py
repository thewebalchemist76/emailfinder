# app.py - Flask Backend per Email Finder
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re
import csv
import io
import time
from urllib.parse import urljoin, urlparse

app = Flask(__name__, static_folder='.')
CORS(app)

# ===== SERVE FRONTEND =====
@app.route('/')
def serve_frontend():
    return send_from_directory('.', 'index.html')


# ===== UTILS =====
def clean_domain(domain):
    """Pulisce il dominio da http, https, www, etc."""
    domain = domain.strip()
    domain = re.sub(r'^https?://', '', domain)
    domain = re.sub(r'^www\.', '', domain)
    domain = re.sub(r'/$', '', domain)
    return domain


def extract_emails_from_text(text, domain):
    """Estrae email dal testo usando regex avanzato"""
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    emails = re.findall(email_pattern, text)

    domain_base = domain.split('.')[0]
    filtered_emails = set()

    for email in emails:
        email_lower = email.lower()
        if (
            domain in email_lower or 
            domain_base in email_lower or
            any(x in email_lower for x in ['info@', 'contact@', 'admin@', 'support@'])
        ):
            filtered_emails.add(email_lower)

    return list(filtered_emails)


def scrape_website(domain):
    """Scarica e analizza le pagine del sito per trovare email"""
    clean_dom = clean_domain(domain)

    paths = [
        '',
        '/contatti',
        '/contattaci',
        '/contact',
        '/contact-us',
        '/chi-siamo',
        '/about',
        '/about-us',
        '/staff',
        '/team',
        '/redazione'
    ]

    all_emails = set()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    for path in paths:
        url = f"https://{clean_dom}{path}"
        try:
            response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')

                # Metodo 1: mailto:
                mailto_links = soup.find_all('a', href=re.compile(r'^mailto:'))
                for link in mailto_links:
                    email = link.get('href').replace('mailto:', '').split('?')[0]
                    all_emails.add(email.lower())

                # Metodo 2: testo visibile
                text = soup.get_text()
                emails = extract_emails_from_text(text, clean_dom)
                all_emails.update(emails)

                # Metodo 3: attributi data-email
                for tag in soup.find_all(attrs={'data-email': True}):
                    all_emails.add(tag['data-email'].lower())

                time.sleep(0.5)

        except Exception as e:
            print(f"Errore su {url}: {str(e)}")
            continue

    return list(all_emails)


# ===== API STATUS (vecchia / ) =====
@app.route('/api/status')
def home():
    return jsonify({
        'status': 'online',
        'service': 'Email Finder API',
        'endpoints': {
            '/api/find-emails': 'POST - Trova email da lista domini',
            '/api/download-csv': 'POST - Scarica risultati in CSV'
        }
    })


# ===== API FIND EMAILS =====
@app.route('/api/find-emails', methods=['POST'])
def find_emails():
    data = request.get_json()
    domains = data.get('domains', [])

    if not domains:
        return jsonify({'error': 'Nessun dominio fornito'}), 400

    results = []

    for domain in domains:
        clean_dom = clean_domain(domain)
        try:
            emails = scrape_website(clean_dom)
            results.append({
                'domain': clean_dom,
                'emails': emails,
                'count': len(emails),
                'status': 'success' if emails else 'empty'
            })
        except Exception as e:
            results.append({
                'domain': clean_dom,
                'emails': [],
                'count': 0,
                'status': 'error',
                'error': str(e)
            })

    return jsonify({
        'success': True,
        'results': results,
        'total_emails': sum(r['count'] for r in results)
    })


# ===== API DOWNLOAD CSV =====
@app.route('/api/download-csv', methods=['POST'])
def download_csv():
    data = request.get_json()
    results = data.get('results', [])

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Dominio', 'Email', 'Count'])

    for result in results:
        domain = result['domain']
        emails = result.get('emails', [])
        if emails:
            for email in emails:
                writer.writerow([domain, email, 1])
        else:
            writer.writerow([domain, 'Nessuna email trovata', 0])

    output.seek(0)
    mem = io.BytesIO()
    mem.write(output.getvalue().encode('utf-8'))
    mem.seek(0)

    return send_file(
        mem,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'email_results_{int(time.time())}.csv'
    )


# ===== RUN SERVER =====
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
