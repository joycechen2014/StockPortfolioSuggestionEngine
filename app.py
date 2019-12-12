from flask import Flask, flash, render_template, request, redirect, url_for, session
from pandas_datareader import data as pdr
import yfinance as yf
from sqlalchemy import *
import datetime, pytz, time
import os.path, json

# fix yahoo
yf.pdr_override()

# set up flask
app = Flask(__name__)
app.secret_key = b'Stock Portfolio Suggestion Engine'

# prepare data
strategies = {
    'e_invest': ['apple', 'adobe', 'nestle'],
    'g_invest': ['vertex', 'netflix', 'tesla'],
    'i_invest': ['vanguard', 'ishares1', 'ishares2'],
    'q_invest': ['general_electric', 'nike', 'disney'],
    'v_invest': ['magna', 'toll', 'vornando']
}
stock_map = {
    'apple': {'name': 'Apple Inc.', 'ticker': 'aapl', 'percent': 25, 'strategy': 'Ethical Investing'},
    'adobe': {'name': 'Adobe Systems Incorporated', 'ticker': 'adbe', 'percent': 50, 'strategy': 'Ethical Investing'},
    'nestle': {'name': 'Nestle SA (ADR)', 'ticker': 'nsrgy', 'percent': 25, 'strategy': 'Ethical Investing'},

    'vertex': {'name': 'Vertex Pharmaceuticals Incorporated', 'ticker': 'vrtx', 'percent': 30, 'strategy': 'Growth Investing'},
    'netflix': {'name': 'Netflix Inc.', 'ticker': 'nflx', 'percent': 30, 'strategy': 'Growth Investing'},
    'tesla': {'name': 'Tesla Inc.', 'ticker': 'tsla', 'percent': 40, 'strategy': 'Growth Investing'},

    'vanguard':
        {'name': 'Vanguard Total Stock Market ETF', 'ticker': 'vti', 'percent': 34, 'strategy': 'Index Investing'},
    'ishares1':
        {'name': 'iShares Core MSCI Total Intl Stk', 'ticker': 'ixus', 'percent': 33, 'strategy': 'Index Investing'},
    'ishares2':
        {'name': 'iShares Core 10+ Year USD Bond', 'ticker': 'iltb', 'percent': 33, 'strategy': 'Index Investing'},

    'general_electric':{'name': 'General Electric Company', 'ticker': 'ge', 'percent': 20, 'strategy': 'Quality Investing'},
    'nike': {'name': 'Nike Inc.', 'ticker': 'nke', 'percent': 20, 'strategy': 'Quality Investing'},
    'disney': {'name': 'Walt Disney Co.', 'ticker': 'dis', 'percent': 60, 'strategy': 'Quality Investing'},

    'magna': {'name': 'Magna International', 'ticker': 'mga', 'percent': 30, 'strategy': 'Value Investing'},
    'toll': {'name': 'Toll Brothers', 'ticker': 'tol', 'percent': 30, 'strategy': 'Value Investing'},
    'vornando': {'name': 'Vornado Realty Trust', 'ticker': 'vno', 'percent': 40, 'strategy': 'Value Investing'}
}

# set up database
engine = create_engine('sqlite:///stocks.db', echo=False)
metadata = MetaData(bind=engine)
stock_db = {}
for stock in stock_map:
    stock_db[stock] = Table(stock, metadata,
                            Column('index', DATETIME, primary_key=True),
                            Column('Open', FLOAT),
                            Column('High', FLOAT),
                            Column('Low', FLOAT),
                            Column('Close', FLOAT),
                            Column('Adj Close', FLOAT),
                            Column('Volume', BIGINT)
                            )
metadata.create_all(engine)


@app.route('/')
def index():
    x = []
    y = []
    if os.path.isfile('history.json'):
        with open('history.json') as f:
            dumps_data = json.load(f)
            amount = dumps_data['amount']
            data = dumps_data['data']
            purchase_now = dumps_data['purchase_now']
            total_now = dumps_data['total_now']
            purchase = dumps_data['purchase']
            total = dumps_data['total']
            profit = dumps_data['profit']
            percent = dumps_data['percent']
            look_back = [str(x) for x in dumps_data['look_back']]
            x = dumps_data['x']
            y = dumps_data['y']

        return render_template('index.html',
                               strategies=strategies, stock_map=stock_map,
                               amount=amount,
                               data=data,
                               purchase_now=purchase_now,
                               total_now=total_now,
                               look_back=look_back,
                               purchase=purchase,
                               total=total,
                               profit=profit,
                               percent=percent,
                               x=x,
                               y=y,
                               nav='history')
    else:
        flash('There is no history data', 'error')
        return render_template('index.html', strategies=strategies, stock_map=stock_map,
                               has_past=os.path.isfile('history.json'))


@app.route('/', methods=['POST'])
def process():
    inputs = {}
    selected = {}
    distribution = {}
    count = 0

    # checking the strategies amount
    for strategy in strategies:
        inputs[strategy] = request.form.get(strategy)
        if inputs[strategy] is not None:
            selected[strategy] = 100.00
            count += 1

    if count == 0 or count > 2:
        flash('Please select 1 or 2 investment strategies', 'error')
        return redirect(url_for('index'))
    elif count == 2:
        selected[request.form.get('first_invest')] = float(request.form.get('first_percent').split()[0])
        selected[request.form.get('second_invest')] = float(request.form.get('second_percent').split()[0])

    # checking the strategies distribution
    count = 0
    for item in selected:
        count += selected[item]
    if count != 100:
        flash('Please make sure all selected investment strategies add up to 100%', 'error')
        return redirect(url_for('index'))

    # get the stock distribution
    for strategy in selected:
        for stock in strategies[strategy]:
            percent = stock_map[stock]['percent']
            distribution[stock] = selected[strategy] * percent / 100

    data = {}
    purchase_now = {}
    total_now = 0
    purchase = {}
    total = {}
    profit = {}
    percent = {}

    look_back = [5, 10]
    now = datetime.datetime.now(pytz.timezone('America/Los_Angeles'))

    # money to invest
    amount = float(request.form['invest_amt'])

    # business days to look back
    days = request.form['days']
    if days:
        days = int(days)
        if days not in look_back:
            look_back.insert(0, days)
    else:
        days = 0
    days_look_back = ((days / 365) + 2) * 114 + days
    print('Look Back Days: ' + str(round(days_look_back, 0)))

    for stock in distribution:
        key = stock_map[stock]['name']
        data[key] = []
        stock_name = stock_map[stock]['ticker']
        start_date = (now - datetime.timedelta(days=days_look_back)).strftime('%Y-%m-%d')
        end_date = now.strftime('%Y-%m-%d')
        print("{} {} {}".format(stock_name, start_date, end_date))
        try:
            download_data = pdr.get_data_yahoo(stock_name, start=start_date, end=end_date)
            for row in download_data.itertuples(index=True, name='Pandas'):
                data[key].append({
                    # 'date': row.Index,
                    'open': row.Open,
                    'high': row.High,
                    'low': row.Low,
                    'close': row.Close,
                    'volume': row.Volume,
                    'adj_close': row._1,
                })
        except Exception:
            # May occur a ValueError: zero-size array to reduction operation maximum which has no identity
            _flashes = session.get('_flashes', [])
            if _flashes is None or len(_flashes) == 0:
                flash('Yahoo financial server is busy. Using the backup offline data as source for now.', 'warning')
            stored_data = readOffline(stock)
            for row in stored_data:
                data[key].append({
                    # 'date': row.index,
                    'open': row.Open,
                    'high': row.High,
                    'low': row.Low,
                    'close': row.Close,
                    'volume': row.Volume,
                    'adj_close': row['Adj Close'],
                })

        # calculate the dollar distribution if bought at this momnet
        purchase_now[key] = {}
        purchase_now[key]['distribution'] = distribution[stock]
        purchase_now[key]['strategy'] = stock_map[stock]['strategy']
        purchase_now[key]['amt_dist'] = amount * distribution[stock] / 100
        purchase_now[key]['share'] = int(purchase_now[key]['amt_dist'] / data[key][-1]['close'])
        total_now += purchase_now[key]['share'] * data[key][-1]['close']

    for day in look_back:
        # calculate the dollar distribution if bought x business days ago
        total[day] = 0
        purchase[day] = {}

        for stock in distribution:
            key = stock_map[stock]['name']
            purchase[day][key] = {}
            purchase[day][key]['distribution'] = distribution[stock]
            purchase[day][key]['old_price'] = data[key][-day]['close']
            purchase[day][key]['amt_dist'] = amount * distribution[stock] / 100
            purchase[day][key]['share'] = int(purchase[day][key]['amt_dist'] / data[key][-day]['close'])
            purchase[day][key]['cur_price'] = data[key][-1]['close']
            purchase[day][key]['cur_value'] = data[key][-1]['close'] * purchase[day][key]['share']
            total[day] += purchase[day][key]['cur_value']

        profit[day] = total[day] - amount
        percent[day] = profit[day] / amount

    x = []
    y = []
    history_purchase = {}
    history_total = {}
    history_day = [1, 2, 3, 4, 5]
    for day in history_day:
        # calculate the dollar distribution if bought x business days ago
        history_total[day] = 0
        history_purchase[day] = {}

        for stock in distribution:
            key = stock_map[stock]['name']
            history_purchase[day][key] = {}
            history_purchase[day][key]['distribution'] = distribution[stock]
            history_purchase[day][key]['old_price'] = data[key][-day]['close']
            history_purchase[day][key]['amt_dist'] = amount * distribution[stock] / 100
            history_purchase[day][key]['share'] = int(history_purchase[day][key]['amt_dist'] / data[key][-day]['close'])
            history_purchase[day][key]['cur_price'] = data[key][-1]['close']
            history_purchase[day][key]['cur_value'] = data[key][-1]['close'] * history_purchase[day][key]['share']
            history_total[day] += history_purchase[day][key]['cur_value']

        x.append(day)
        y.append(round(history_total[day], 2))

    dumps_data = {
        'amount': amount,
        'data': data,
        'purchase_now': purchase_now,
        'total_now': total_now,
        'look_back': look_back,
        'purchase': purchase,
        'total': total,
        'profit': profit,
        'percent': percent,
        'x': x,
        'y': y
    }
    with open('history.json', 'w+') as f:
        json.dump(dumps_data, f)

    return render_template('index.html',
                           amount=amount,
                           data=data,
                           purchase_now=purchase_now,
                           total_now=total_now,
                           look_back=look_back,
                           purchase=purchase,
                           total=total,
                           profit=profit,
                           percent=percent,
                           x=x,
                           y=y,
                           nav='result')


def backupData():
    now = datetime.datetime.now(pytz.timezone('America/Los_Angeles'))
    for stock in stock_map:
        start_date = (now - datetime.timedelta(days=1000)).strftime('%Y-%m-%d')
        end_date = now.strftime('%Y-%m-%d')
        download_data = pdr.get_data_yahoo(stock_map[stock]['ticker'],
                                           start=start_date,
                                           end=end_date)
        download_data.to_sql(stock, con=engine, if_exists='replace', index_label='index')


def readOffline(stock):
    count = 0
    while count < 2:
        try:
            return stock_db[stock].select().execute()
        except Exception as e:
            print(e)
            count += 1
            time.sleep(1)
    stock_db[stock] = Table(stock, metadata,
                            Column('index', DATETIME, primary_key=True),
                            Column('Open', FLOAT),
                            Column('High', FLOAT),
                            Column('Low', FLOAT),
                            Column('Close', FLOAT),
                            Column('Adj Close', FLOAT),
                            Column('Volume', BIGINT)
                            )
    return stock_db[stock].select().execute()


@app.errorhandler(404)
def page_not_found(e):
    flash('Dude, what are you looking for?', 'error')
    print(e)
    return redirect(url_for('index'))


@app.errorhandler(Exception)
def http_error_handler(e):
    flash('Oops, the online server is unstable for now, please try later or contact the team to restart the server',
          'error')
    print(e)
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run()
