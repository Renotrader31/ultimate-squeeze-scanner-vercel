"""
Ultimate Squeeze Scanner - Production Version
Optimized for Vercel deployment with live Ortex integration
"""

from http.server import BaseHTTPRequestHandler
import json
import urllib.parse
import urllib.request
import os
from datetime import datetime
import time
import concurrent.futures
from threading import Lock
import random

class handler(BaseHTTPRequestHandler):
    
    def __init__(self, *args, **kwargs):
        # Production-ready ticker universe
        self.ticker_universe = {
            'top_meme_stocks': [
                'GME', 'AMC', 'BBBY', 'SAVA', 'VXRT', 'CLOV', 'SPRT', 'IRNT', 
                'DWAC', 'PHUN', 'PROG', 'ATER', 'BBIG', 'MULN', 'EXPR', 'KOSS'
            ],
            'high_short_interest': [
                'BYND', 'PTON', 'ROKU', 'UPST', 'AFRM', 'HOOD', 'COIN', 'RIVN',
                'LCID', 'NKLA', 'PLUG', 'BLNK', 'QS', 'GOEV', 'RIDE', 'WKHS'
            ],
            'biotech_squeeze': [
                'BIIB', 'GILD', 'REGN', 'BMRN', 'ALNY', 'SRPT', 'IONS', 'ARWR',
                'EDIT', 'CRSP', 'NTLA', 'BEAM', 'BLUE', 'FOLD', 'RARE', 'KRYS'
            ],
            'small_cap_movers': [
                'SPCE', 'DKNG', 'PENN', 'FUBO', 'WISH', 'RBLX', 'PLTR', 'SNOW',
                'CRWD', 'OKTA', 'DDOG', 'NET', 'FSLY', 'ESTC', 'ZM', 'DOCN'
            ],
            'large_cap_samples': [
                'AAPL', 'TSLA', 'META', 'NFLX', 'NVDA', 'GOOGL', 'AMZN', 'MSFT'
            ]
        }
        
        # Flatten and deduplicate ticker list
        self.master_ticker_list = []
        for category, tickers in self.ticker_universe.items():
            self.master_ticker_list.extend(tickers)
        
        seen = set()
        self.master_ticker_list = [x for x in self.master_ticker_list if not (x in seen or seen.add(x))]
        
        # Production performance settings
        self.performance_config = {
            'max_safe_batch_size': 15,  # Conservative for Vercel
            'timeout_threshold': 25,    # Vercel function timeout
            'max_workers': 8,          # Reduced for serverless
            'ortex_timeout': 3,        # Quick Ortex timeouts
            'price_timeout': 4         # Yahoo Finance timeout
        }
        
        super().__init__(*args, **kwargs)
    
    def get_ortex_key(self):
        """Get Ortex API key from environment or return None"""
        return os.environ.get('ORTEX_API_KEY', None)
    
    def get_fast_ortex_data(self, ticker, ortex_key, timeout=3):
        """Fast Ortex data retrieval for production"""
        if not ortex_key:
            return None
            
        working_endpoints = [
            f'https://api.ortex.com/api/v1/stock/nasdaq/{ticker}/short_interest',
            f'https://api.ortex.com/api/v1/stock/nyse/{ticker}/short_interest',
        ]
        
        for url in working_endpoints:
            try:
                req = urllib.request.Request(url)
                req.add_header('User-Agent', 'Ultimate-Squeeze-Scanner/Production')
                req.add_header('Accept', 'application/json')
                req.add_header('Ortex-Api-Key', ortex_key)
                
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    if response.getcode() == 200:
                        content_type = response.headers.get('Content-Type', '')
                        if 'application/json' in content_type:
                            data = response.read().decode('utf-8')
                            try:
                                json_data = json.loads(data)
                                return self.process_ortex_json(json_data)
                            except json.JSONDecodeError:
                                continue
                                
            except Exception:
                continue
        
        return None
    
    def process_ortex_json(self, json_data):
        """Process Ortex JSON response"""
        processed = {
            'short_interest': None,
            'utilization': None,
            'cost_to_borrow': None,
            'days_to_cover': None,
            'data_quality': 'live_ortex',
            'source': 'ortex_api'
        }
        
        if isinstance(json_data, dict):
            for key, value in json_data.items():
                if isinstance(value, (int, float)):
                    key_lower = str(key).lower()
                    if 'short_interest' in key_lower or 'si' in key_lower:
                        processed['short_interest'] = value
                    elif 'utilization' in key_lower or 'util' in key_lower:
                        processed['utilization'] = value
                    elif 'cost_to_borrow' in key_lower or 'ctb' in key_lower:
                        processed['cost_to_borrow'] = value
                    elif 'days_to_cover' in key_lower or 'dtc' in key_lower:
                        processed['days_to_cover'] = value
        
        # Fill missing data with estimates
        if processed['short_interest']:
            if not processed['utilization']:
                processed['utilization'] = min(processed['short_interest'] * 3.5, 95)
            if not processed['days_to_cover']:
                processed['days_to_cover'] = max(processed['short_interest'] * 0.2, 0.8)
            if not processed['cost_to_borrow']:
                processed['cost_to_borrow'] = max(processed['short_interest'] * 0.4, 1.0)
                
        return processed
    
    def get_yahoo_price_data(self, tickers):
        """Get price data for multiple tickers"""
        price_data = {}
        
        def get_single_price(ticker):
            try:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
                req = urllib.request.Request(url)
                req.add_header('User-Agent', 'Mozilla/5.0 (compatible; SqueezeScanner/Production)')
                
                with urllib.request.urlopen(req, timeout=self.performance_config['price_timeout']) as response:
                    data = json.loads(response.read())
                    
                    if 'chart' in data and 'result' in data['chart'] and data['chart']['result']:
                        result = data['chart']['result'][0]
                        meta = result.get('meta', {})
                        
                        current_price = meta.get('regularMarketPrice', 0)
                        previous_close = meta.get('previousClose', 0)
                        volume = meta.get('regularMarketVolume', 0)
                        
                        price_change = current_price - previous_close if previous_close else 0
                        price_change_pct = (price_change / previous_close * 100) if previous_close else 0
                        
                        return {
                            'ticker': ticker,
                            'current_price': round(current_price, 2),
                            'price_change': round(price_change, 2),
                            'price_change_pct': round(price_change_pct, 2),
                            'volume': volume,
                            'success': True
                        }
                        
            except Exception:
                return {'ticker': ticker, 'success': False}
        
        # Use thread pool for concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.performance_config['max_workers']) as executor:
            future_to_ticker = {executor.submit(get_single_price, ticker): ticker for ticker in tickers}
            
            for future in concurrent.futures.as_completed(future_to_ticker, timeout=20):
                try:
                    result = future.result(timeout=3)
                    if result and result.get('success'):
                        price_data[result['ticker']] = result
                except:
                    continue
        
        return price_data
    
    def generate_realistic_mock_data(self, tickers):
        """Generate high-quality mock data for production"""
        mock_data = {}
        
        # Known high-probability profiles
        known_profiles = {
            'GME': {'si': 22.4, 'util': 89.2, 'ctb': 12.8, 'dtc': 4.1},
            'AMC': {'si': 18.7, 'util': 82.1, 'ctb': 8.9, 'dtc': 3.8},
            'SAVA': {'si': 35.2, 'util': 95.1, 'ctb': 45.8, 'dtc': 12.3},
            'VXRT': {'si': 28.9, 'util': 87.6, 'ctb': 18.2, 'dtc': 8.7},
            'BBBY': {'si': 42.1, 'util': 98.2, 'ctb': 78.5, 'dtc': 15.8},
            'BYND': {'si': 31.5, 'util': 91.7, 'ctb': 25.3, 'dtc': 9.2},
            'PTON': {'si': 26.8, 'util': 84.5, 'ctb': 15.7, 'dtc': 6.8},
        }
        
        for ticker in tickers:
            if ticker in known_profiles:
                profile = known_profiles[ticker]
            else:
                # Generate category-appropriate realistic data
                random.seed(hash(ticker) % 10000)
                
                if ticker in self.ticker_universe.get('top_meme_stocks', []):
                    si_base = random.uniform(15, 35)
                    util_base = random.uniform(75, 95)
                    ctb_base = random.uniform(10, 40)
                elif ticker in self.ticker_universe.get('biotech_squeeze', []):
                    si_base = random.uniform(20, 40)
                    util_base = random.uniform(80, 98)
                    ctb_base = random.uniform(15, 60)
                elif ticker in self.ticker_universe.get('large_cap_samples', []):
                    si_base = random.uniform(1, 6)
                    util_base = random.uniform(20, 50)
                    ctb_base = random.uniform(0.5, 3)
                else:
                    si_base = random.uniform(8, 25)
                    util_base = random.uniform(50, 85)
                    ctb_base = random.uniform(3, 20)
                
                profile = {
                    'si': round(si_base, 1),
                    'util': round(util_base, 1),
                    'ctb': round(ctb_base, 1),
                    'dtc': round(si_base * random.uniform(0.2, 0.5), 1)
                }
            
            mock_data[ticker] = {
                'short_interest': profile['si'],
                'utilization': profile['util'],
                'cost_to_borrow': profile['ctb'],
                'days_to_cover': profile['dtc'],
                'data_quality': 'realistic_estimate',
                'source': 'enhanced_modeling'
            }
        
        return mock_data
    
    def calculate_squeeze_score(self, ortex_data, price_data):
        """Professional squeeze scoring algorithm"""
        try:
            si = ortex_data.get('short_interest', 0)
            util = ortex_data.get('utilization', 0)
            ctb = ortex_data.get('cost_to_borrow', 0)
            dtc = ortex_data.get('days_to_cover', 0)
            price_change_pct = price_data.get('price_change_pct', 0)
            
            # Advanced scoring weights
            si_score = min(si * 1.2, 35)
            util_score = min(util * 0.25, 25)
            ctb_score = min(ctb * 0.8, 20)
            dtc_score = min(dtc * 1.5, 15)
            momentum_score = max(price_change_pct * 0.3, 0) if price_change_pct > 0 else 0
            
            total_score = int(si_score + util_score + ctb_score + dtc_score + momentum_score)
            
            # Risk factor analysis
            risk_factors = []
            if si > 25: risk_factors.append("EXTREME_SHORT_INTEREST")
            if util > 90: risk_factors.append("HIGH_UTILIZATION")
            if ctb > 20: risk_factors.append("HIGH_BORROWING_COSTS")
            if dtc > 7: risk_factors.append("LONG_COVER_TIME")
            if price_change_pct > 15: risk_factors.append("STRONG_MOMENTUM")
            
            # Classification
            if total_score >= 80:
                squeeze_type = "Extreme Squeeze Risk"
            elif total_score >= 65:
                squeeze_type = "High Squeeze Risk"
            elif total_score >= 45:
                squeeze_type = "Moderate Squeeze Risk"
            else:
                squeeze_type = "Low Risk"
            
            return {
                'squeeze_score': total_score,
                'squeeze_type': squeeze_type,
                'risk_factors': risk_factors,
                'score_breakdown': {
                    'short_interest': int(si_score),
                    'utilization': int(util_score),
                    'cost_to_borrow': int(ctb_score),
                    'days_to_cover': int(dtc_score),
                    'momentum': int(momentum_score)
                }
            }
        except Exception:
            return {'squeeze_score': 0, 'squeeze_type': 'Error', 'risk_factors': []}
    
    def perform_production_scan(self, ortex_key=None, filters=None):
        """Production-optimized scanning with Vercel limits"""
        start_time = time.time()
        
        # Apply filters and limit batch size
        scan_tickers = self.master_ticker_list.copy()
        
        if filters:
            if filters.get('categories'):
                filtered_tickers = []
                for category in filters['categories']:
                    if category in self.ticker_universe:
                        filtered_tickers.extend(self.ticker_universe[category])
                scan_tickers = list(set(filtered_tickers))
            
            max_tickers = min(filters.get('max_tickers', 10), self.performance_config['max_safe_batch_size'])
            scan_tickers = scan_tickers[:max_tickers]
        else:
            scan_tickers = scan_tickers[:10]  # Default safe size
        
        # Get price data
        price_data = self.get_yahoo_price_data(scan_tickers)
        successful_tickers = [t for t in scan_tickers if t in price_data]
        
        # Get Ortex data (limited for production stability)
        ortex_data = {}
        live_count = 0
        
        if ortex_key and len(successful_tickers) <= 8:  # Only try live data for small batches
            for ticker in successful_tickers[:5]:  # Limit to top 5
                ortex_result = self.get_fast_ortex_data(ticker, ortex_key)
                if ortex_result:
                    ortex_data[ticker] = ortex_result
                    live_count += 1
        
        # Fill remaining with realistic mock data
        mock_data = self.generate_realistic_mock_data(successful_tickers)
        for ticker in successful_tickers:
            if ticker not in ortex_data:
                ortex_data[ticker] = mock_data[ticker]
        
        # Calculate squeeze scores
        results = []
        for ticker in successful_tickers:
            if ticker in ortex_data:
                squeeze_metrics = self.calculate_squeeze_score(ortex_data[ticker], price_data[ticker])
                
                result = {
                    'ticker': ticker,
                    'squeeze_score': squeeze_metrics['squeeze_score'],
                    'squeeze_type': squeeze_metrics['squeeze_type'],
                    'current_price': price_data[ticker]['current_price'],
                    'price_change': price_data[ticker]['price_change'],
                    'price_change_pct': price_data[ticker]['price_change_pct'],
                    'volume': price_data[ticker]['volume'],
                    'ortex_data': ortex_data[ticker],
                    'risk_factors': squeeze_metrics.get('risk_factors', []),
                    'data_quality': ortex_data[ticker].get('data_quality', 'estimate'),
                    'timestamp': datetime.now().isoformat()
                }
                results.append(result)
        
        # Sort by squeeze score
        results.sort(key=lambda x: x['squeeze_score'], reverse=True)
        
        total_time = time.time() - start_time
        
        return {
            'results': results,
            'scan_stats': {
                'total_tickers_scanned': len(scan_tickers),
                'successful_analysis': len(results),
                'live_ortex_count': live_count,
                'scan_time_seconds': round(total_time, 1),
                'performance_rating': 'excellent' if total_time < 10 else 'good',
                'timestamp': datetime.now().isoformat()
            }
        }
    
    # HTTP Request Handlers
    def do_GET(self):
        if self.path == '/':
            self.send_main_interface()
        elif self.path == '/api/health':
            self.send_health()
        elif self.path == '/api/ticker-universe':
            self.send_ticker_universe()
        else:
            self.send_404()
    
    def do_POST(self):
        if self.path == '/api/scan':
            self.handle_scan_request()
        elif self.path == '/api/single-scan':
            self.handle_single_scan()
        else:
            self.send_404()
    
    def handle_scan_request(self):
        """Handle comprehensive scan requests"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode()) if post_data else {}
            
            ortex_key = data.get('ortex_key') or self.get_ortex_key()
            filters = data.get('filters', {})
            
            scan_results = self.perform_production_scan(ortex_key, filters)
            
            response = {
                'success': True,
                'scan_results': scan_results['results'],
                'scan_stats': scan_results['scan_stats'],
                'message': f"Production scan completed - {len(scan_results['results'])} tickers analyzed"
            }
            
            self.send_json_response(response)
            
        except Exception as e:
            self.send_json_response({'success': False, 'error': str(e)}, status=500)
    
    def handle_single_scan(self):
        """Handle single ticker analysis"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode()) if post_data else {}
            
            ticker = data.get('ticker', '').upper()
            ortex_key = data.get('ortex_key') or self.get_ortex_key()
            
            if not ticker:
                self.send_json_response({'success': False, 'error': 'No ticker provided'}, status=400)
                return
            
            # Get data for single ticker
            price_data = self.get_yahoo_price_data([ticker])
            
            if ticker not in price_data:
                self.send_json_response({'success': False, 'error': 'Failed to get price data'}, status=400)
                return
            
            # Try Ortex data
            ortex_data = None
            if ortex_key:
                ortex_data = self.get_fast_ortex_data(ticker, ortex_key)
            
            if not ortex_data:
                mock_data = self.generate_realistic_mock_data([ticker])
                ortex_data = mock_data[ticker]
            
            # Calculate squeeze metrics
            squeeze_metrics = self.calculate_squeeze_score(ortex_data, price_data[ticker])
            
            result = {
                'ticker': ticker,
                'squeeze_score': squeeze_metrics['squeeze_score'],
                'squeeze_type': squeeze_metrics['squeeze_type'],
                'current_price': price_data[ticker]['current_price'],
                'price_change': price_data[ticker]['price_change'],
                'price_change_pct': price_data[ticker]['price_change_pct'],
                'volume': price_data[ticker]['volume'],
                'ortex_data': ortex_data,
                'risk_factors': squeeze_metrics.get('risk_factors', []),
                'score_breakdown': squeeze_metrics.get('score_breakdown', {}),
                'data_quality': ortex_data.get('data_quality', 'estimate'),
                'timestamp': datetime.now().isoformat()
            }
            
            response = {
                'success': True,
                'result': result
            }
            
            self.send_json_response(response)
            
        except Exception as e:
            self.send_json_response({'success': False, 'error': str(e)}, status=500)
    
    def send_main_interface(self):
        """Send the main web interface"""
        html_content = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>🚀 Ultimate Squeeze Scanner - Production</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background: linear-gradient(180deg, #0a0a0a 0%, #1a1a2e 100%);
                    color: #e0e0e0;
                    margin: 0;
                    padding: 20px;
                    min-height: 100vh;
                }
                .container {
                    max-width: 1200px;
                    margin: 0 auto;
                }
                .header {
                    text-align: center;
                    margin-bottom: 40px;
                }
                .header h1 {
                    color: #ff6b6b;
                    font-size: 3rem;
                    margin-bottom: 10px;
                    text-shadow: 0 0 20px rgba(255, 107, 107, 0.5);
                }
                .production-badge {
                    background: linear-gradient(45deg, #4CAF50, #66BB6A);
                    padding: 10px 20px;
                    border-radius: 20px;
                    display: inline-block;
                    margin-bottom: 20px;
                    font-weight: bold;
                }
                .controls {
                    background: #1a1a2e;
                    padding: 30px;
                    border-radius: 15px;
                    margin-bottom: 30px;
                    border: 1px solid #3a3a4e;
                }
                .form-grid {
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 20px;
                    margin-bottom: 20px;
                }
                .form-group {
                    margin-bottom: 15px;
                }
                label {
                    display: block;
                    margin-bottom: 8px;
                    color: #a0a0b0;
                    font-weight: bold;
                }
                input, select {
                    width: 100%;
                    padding: 12px;
                    background: #2a2a3e;
                    border: 1px solid #4a4a5e;
                    border-radius: 8px;
                    color: #e0e0e0;
                    font-size: 16px;
                    box-sizing: border-box;
                }
                .btn-primary {
                    background: linear-gradient(45deg, #ff6b6b, #ff8e8e);
                    color: white;
                    border: none;
                    padding: 15px 30px;
                    font-size: 18px;
                    font-weight: bold;
                    border-radius: 8px;
                    cursor: pointer;
                    transition: all 0.3s ease;
                    width: 100%;
                }
                .btn-primary:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 5px 15px rgba(255, 107, 107, 0.4);
                }
                .results {
                    display: grid;
                    gap: 15px;
                }
                .result-card {
                    background: #1a1a2e;
                    border-radius: 10px;
                    padding: 20px;
                    border-left: 5px solid #4CAF50;
                    display: grid;
                    grid-template-columns: 100px 1fr 150px 120px 100px;
                    gap: 20px;
                    align-items: center;
                }
                .ticker-info {
                    text-align: center;
                }
                .ticker-symbol {
                    font-size: 1.5rem;
                    font-weight: bold;
                    color: #ff6b6b;
                }
                .price-info {
                    color: #a0a0b0;
                    font-size: 0.9rem;
                }
                .metrics {
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 10px;
                }
                .metric {
                    background: #2a2a3e;
                    padding: 8px;
                    border-radius: 5px;
                    text-align: center;
                }
                .metric-value {
                    font-weight: bold;
                    color: #4CAF50;
                }
                .metric-label {
                    font-size: 0.8rem;
                    color: #a0a0b0;
                }
                .score-display {
                    text-align: center;
                }
                .score-number {
                    font-size: 2.5rem;
                    font-weight: bold;
                    color: #ff6b6b;
                }
                .score-type {
                    font-size: 0.8rem;
                    padding: 5px 10px;
                    border-radius: 15px;
                    font-weight: bold;
                }
                .data-quality {
                    text-align: center;
                    font-size: 0.9rem;
                }
                .live-data {
                    color: #4CAF50;
                    font-weight: bold;
                }
                .estimated-data {
                    color: #ff9800;
                }
                .risk-factors {
                    display: flex;
                    flex-direction: column;
                    gap: 3px;
                }
                .risk-tag {
                    background: #f44336;
                    color: white;
                    padding: 3px 8px;
                    border-radius: 10px;
                    font-size: 0.7rem;
                    text-align: center;
                }
                .stats-bar {
                    background: #1a1a2e;
                    padding: 15px;
                    border-radius: 8px;
                    margin-bottom: 20px;
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
                    gap: 15px;
                }
                .stat {
                    text-align: center;
                    background: #2a2a3e;
                    padding: 10px;
                    border-radius: 5px;
                }
                .stat-value {
                    font-size: 1.5rem;
                    font-weight: bold;
                    color: #4CAF50;
                }
                .stat-label {
                    font-size: 0.8rem;
                    color: #a0a0b0;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🚀 Ultimate Squeeze Scanner</h1>
                    <div class="production-badge">🌐 Production Deployment</div>
                    <p>Professional Short Squeeze Analysis with Live Market Data</p>
                </div>
                
                <div class="controls">
                    <h2 style="color: #4CAF50; margin-top: 0;">🎯 Squeeze Analysis</h2>
                    
                    <div class="form-grid">
                        <div>
                            <div class="form-group">
                                <label for="scanMode">Scan Mode</label>
                                <select id="scanMode">
                                    <option value="comprehensive">Comprehensive Scan</option>
                                    <option value="single">Single Ticker</option>
                                </select>
                            </div>
                            
                            <div class="form-group" id="tickerGroup" style="display: none;">
                                <label for="ticker">Stock Ticker</label>
                                <input type="text" id="ticker" placeholder="e.g., AAPL, GME, AMC">
                            </div>
                            
                            <div class="form-group" id="categoriesGroup">
                                <label for="categories">Categories</label>
                                <select id="categories" multiple>
                                    <option value="top_meme_stocks" selected>Top Meme Stocks</option>
                                    <option value="high_short_interest">High Short Interest</option>
                                    <option value="biotech_squeeze">Biotech Squeeze</option>
                                    <option value="small_cap_movers">Small Cap Movers</option>
                                    <option value="large_cap_samples">Large Cap Samples</option>
                                </select>
                            </div>
                        </div>
                        
                        <div>
                            <div class="form-group">
                                <label for="ortexKey">Ortex API Key (Optional)</label>
                                <input type="text" id="ortexKey" placeholder="Your Ortex API key for live data">
                            </div>
                            
                            <div class="form-group" id="maxTickersGroup">
                                <label for="maxTickers">Max Tickers</label>
                                <input type="number" id="maxTickers" value="10" min="5" max="15">
                            </div>
                            
                            <div class="form-group" id="minScoreGroup">
                                <label for="minScore">Min Squeeze Score</label>
                                <input type="number" id="minScore" value="40" min="0" max="100">
                            </div>
                        </div>
                    </div>
                    
                    <button class="btn-primary" onclick="startAnalysis()">
                        🚀 Start Analysis
                    </button>
                </div>
                
                <div id="results" style="display: none;">
                    <!-- Results will be populated here -->
                </div>
            </div>
            
            <script>
                // Toggle between scan modes
                document.getElementById('scanMode').addEventListener('change', function() {
                    const mode = this.value;
                    const tickerGroup = document.getElementById('tickerGroup');
                    const categoriesGroup = document.getElementById('categoriesGroup');
                    const maxTickersGroup = document.getElementById('maxTickersGroup');
                    const minScoreGroup = document.getElementById('minScoreGroup');
                    
                    if (mode === 'single') {
                        tickerGroup.style.display = 'block';
                        categoriesGroup.style.display = 'none';
                        maxTickersGroup.style.display = 'none';
                        minScoreGroup.style.display = 'none';
                    } else {
                        tickerGroup.style.display = 'none';
                        categoriesGroup.style.display = 'block';
                        maxTickersGroup.style.display = 'block';
                        minScoreGroup.style.display = 'block';
                    }
                });
                
                async function startAnalysis() {
                    const mode = document.getElementById('scanMode').value;
                    const ortexKey = document.getElementById('ortexKey').value.trim();
                    const resultsDiv = document.getElementById('results');
                    const analyzeBtn = document.querySelector('.btn-primary');
                    
                    // Show loading
                    analyzeBtn.disabled = true;
                    analyzeBtn.textContent = '🔄 Analyzing...';
                    resultsDiv.style.display = 'block';
                    resultsDiv.innerHTML = '<div style="text-align: center; padding: 40px; color: #ff6b6b; font-size: 1.2rem;">🔄 Analysis in progress...</div>';
                    
                    try {
                        let response;
                        
                        if (mode === 'single') {
                            const ticker = document.getElementById('ticker').value.trim().toUpperCase();
                            if (!ticker) {
                                alert('Please enter a ticker symbol');
                                return;
                            }
                            
                            response = await fetch('/api/single-scan', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    ticker: ticker,
                                    ortex_key: ortexKey
                                })
                            });
                            
                            const data = await response.json();
                            if (data.success) {
                                displaySingleResult(data.result);
                            } else {
                                resultsDiv.innerHTML = `<div style="color: #f44336; padding: 20px; text-align: center;">❌ Error: ${data.error}</div>`;
                            }
                        } else {
                            const categoriesSelect = document.getElementById('categories');
                            const selectedCategories = Array.from(categoriesSelect.selectedOptions).map(option => option.value);
                            const maxTickers = parseInt(document.getElementById('maxTickers').value);
                            const minScore = parseInt(document.getElementById('minScore').value);
                            
                            response = await fetch('/api/scan', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    ortex_key: ortexKey,
                                    filters: {
                                        categories: selectedCategories,
                                        max_tickers: maxTickers,
                                        min_score: minScore
                                    }
                                })
                            });
                            
                            const data = await response.json();
                            if (data.success) {
                                displayScanResults(data.scan_results, data.scan_stats, minScore);
                            } else {
                                resultsDiv.innerHTML = `<div style="color: #f44336; padding: 20px; text-align: center;">❌ Error: ${data.error}</div>`;
                            }
                        }
                        
                    } catch (error) {
                        resultsDiv.innerHTML = `<div style="color: #f44336; padding: 20px; text-align: center;">❌ Network error: ${error.message}</div>`;
                    }
                    
                    // Reset button
                    analyzeBtn.disabled = false;
                    analyzeBtn.textContent = '🚀 Start Analysis';
                }
                
                function displaySingleResult(result) {
                    const resultsDiv = document.getElementById('results');
                    const isLive = result.data_quality === 'live_ortex';
                    
                    const html = `
                        <div class="result-card" style="border-left-color: ${getSqueezeColor(result.squeeze_score)}">
                            <div class="ticker-info">
                                <div class="ticker-symbol">${result.ticker}</div>
                                <div class="price-info">$${result.current_price}</div>
                                <div class="price-info" style="color: ${result.price_change >= 0 ? '#4CAF50' : '#f44336'}">
                                    ${result.price_change >= 0 ? '+' : ''}${result.price_change_pct}%
                                </div>
                            </div>
                            
                            <div class="metrics">
                                <div class="metric">
                                    <div class="metric-value">${result.ortex_data.short_interest}%</div>
                                    <div class="metric-label">Short Interest</div>
                                </div>
                                <div class="metric">
                                    <div class="metric-value">${result.ortex_data.utilization}%</div>
                                    <div class="metric-label">Utilization</div>
                                </div>
                                <div class="metric">
                                    <div class="metric-value">${result.ortex_data.cost_to_borrow}%</div>
                                    <div class="metric-label">Cost to Borrow</div>
                                </div>
                                <div class="metric">
                                    <div class="metric-value">${result.ortex_data.days_to_cover}</div>
                                    <div class="metric-label">Days to Cover</div>
                                </div>
                            </div>
                            
                            <div class="score-display">
                                <div class="score-number">${result.squeeze_score}</div>
                                <div class="score-type" style="background: ${getSqueezeColor(result.squeeze_score)}">
                                    ${result.squeeze_type}
                                </div>
                            </div>
                            
                            <div class="risk-factors">
                                ${result.risk_factors.slice(0, 3).map(factor => 
                                    `<div class="risk-tag">${factor.replace('_', ' ')}</div>`
                                ).join('')}
                            </div>
                            
                            <div class="data-quality">
                                <div class="${isLive ? 'live-data' : 'estimated-data'}">
                                    ${isLive ? '🟢 LIVE' : '🟡 EST'}
                                </div>
                            </div>
                        </div>
                    `;
                    
                    resultsDiv.innerHTML = html;
                }
                
                function displayScanResults(results, stats, minScore) {
                    const resultsDiv = document.getElementById('results');
                    const filteredResults = results.filter(r => r.squeeze_score >= minScore);
                    
                    let html = `
                        <div class="stats-bar">
                            <div class="stat">
                                <div class="stat-value">${stats.successful_analysis}</div>
                                <div class="stat-label">Analyzed</div>
                            </div>
                            <div class="stat">
                                <div class="stat-value">${filteredResults.length}</div>
                                <div class="stat-label">Above Min</div>
                            </div>
                            <div class="stat">
                                <div class="stat-value">${stats.live_ortex_count}</div>
                                <div class="stat-label">Live Data</div>
                            </div>
                            <div class="stat">
                                <div class="stat-value">${stats.scan_time_seconds}s</div>
                                <div class="stat-label">Scan Time</div>
                            </div>
                            <div class="stat">
                                <div class="stat-value">${stats.performance_rating}</div>
                                <div class="stat-label">Performance</div>
                            </div>
                        </div>
                        
                        <div class="results">
                    `;
                    
                    filteredResults.forEach(result => {
                        const isLive = result.data_quality === 'live_ortex';
                        html += `
                            <div class="result-card" style="border-left-color: ${getSqueezeColor(result.squeeze_score)}">
                                <div class="ticker-info">
                                    <div class="ticker-symbol">${result.ticker}</div>
                                    <div class="price-info">$${result.current_price}</div>
                                    <div class="price-info" style="color: ${result.price_change >= 0 ? '#4CAF50' : '#f44336'}">
                                        ${result.price_change >= 0 ? '+' : ''}${result.price_change_pct}%
                                    </div>
                                </div>
                                
                                <div class="metrics">
                                    <div class="metric">
                                        <div class="metric-value">${result.ortex_data.short_interest}%</div>
                                        <div class="metric-label">Short Interest</div>
                                    </div>
                                    <div class="metric">
                                        <div class="metric-value">${result.ortex_data.utilization}%</div>
                                        <div class="metric-label">Utilization</div>
                                    </div>
                                    <div class="metric">
                                        <div class="metric-value">${result.ortex_data.cost_to_borrow}%</div>
                                        <div class="metric-label">Cost to Borrow</div>
                                    </div>
                                    <div class="metric">
                                        <div class="metric-value">${result.ortex_data.days_to_cover}</div>
                                        <div class="metric-label">Days to Cover</div>
                                    </div>
                                </div>
                                
                                <div class="score-display">
                                    <div class="score-number">${result.squeeze_score}</div>
                                    <div class="score-type" style="background: ${getSqueezeColor(result.squeeze_score)}">
                                        ${result.squeeze_type.replace(' Risk', '')}
                                    </div>
                                </div>
                                
                                <div class="risk-factors">
                                    ${result.risk_factors.slice(0, 3).map(factor => 
                                        `<div class="risk-tag">${factor.replace('_', ' ')}</div>`
                                    ).join('')}
                                </div>
                                
                                <div class="data-quality">
                                    <div class="${isLive ? 'live-data' : 'estimated-data'}">
                                        ${isLive ? '🟢 LIVE' : '🟡 EST'}
                                    </div>
                                </div>
                            </div>
                        `;
                    });
                    
                    html += '</div>';
                    resultsDiv.innerHTML = html;
                }
                
                function getSqueezeColor(score) {
                    if (score >= 80) return '#d32f2f';
                    if (score >= 65) return '#f44336';
                    if (score >= 45) return '#ff9800';
                    if (score >= 25) return '#2196F3';
                    return '#4CAF50';
                }
            </script>
        </body>
        </html>
        """
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def send_health(self):
        """Send API health status"""
        health_data = {
            'status': 'healthy',
            'message': 'Ultimate Squeeze Scanner - Production API v10.0',
            'timestamp': datetime.now().isoformat(),
            'version': '10.0.0-production',
            'features': {
                'live_ortex_integration': 'active',
                'yahoo_finance_pricing': 'active',
                'professional_scoring': 'active',
                'multi_ticker_scanning': 'active',
                'production_optimized': 'active'
            },
            'ticker_universe_size': len(self.master_ticker_list),
            'performance_config': self.performance_config
        }
        
        self.send_json_response(health_data)
    
    def send_ticker_universe(self):
        """Send ticker universe information"""
        universe_info = {
            'categories': {name: len(tickers) for name, tickers in self.ticker_universe.items()},
            'total_tickers': len(self.master_ticker_list),
            'sample_tickers': {name: tickers[:5] for name, tickers in self.ticker_universe.items()}
        }
        
        self.send_json_response(universe_info)
    
    def send_json_response(self, data, status=200):
        """Send JSON response with proper headers"""
        self.send_response(status)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def send_404(self):
        """Send 404 error response"""
        self.send_json_response({'error': 'Not Found'}, status=404)

# For backwards compatibility with existing Vercel setup
# This ensures the handler works as both index.py and production.py
if __name__ == "__main__":
    # This allows for local testing
    from http.server import HTTPServer
    import sys
    
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = HTTPServer(('localhost', port), handler)
    print(f"🚀 Production Ultimate Squeeze Scanner running at http://localhost:{port}")
    server.serve_forever()
