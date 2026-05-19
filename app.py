import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, g

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, 'database.db')


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        g._database = db
    return db


def close_db(e=None):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


app = Flask(__name__)
app.secret_key = 'please_change_this_secret'
app.teardown_appcontext(close_db)


@app.route('/')
def index():
    db = get_db()
    try:
        cur = db.execute(
            """
            SELECT o.order_id, o.order_time, o.order_status,
                   s.session_id, s.table_id, t.table_number,
                   od.detail_id, od.quantity, od.note,
                   m.menu_id, m.menu_name, m.image_url
            FROM Orders o
            JOIN Order_Details od ON o.order_id = od.order_id
            JOIN Menu m ON od.menu_id = m.menu_id
            JOIN Sessions s ON o.session_id = s.session_id
            JOIN Tables t ON s.table_id = t.table_id
            WHERE COALESCE(o.order_status, '') NOT IN ('completed', 'cancelled')
            ORDER BY o.order_time DESC
            """
        )
        rows = cur.fetchall()

        orders = {}
        for r in rows:
            oid = r['order_id']
            if oid not in orders:
                orders[oid] = {
                    'order_id': oid,
                    'order_time': r['order_time'],
                    'order_status': r['order_status'],
                    'session_id': r['session_id'],
                    'table_number': r['table_number'],
                    'items': [],
                }
            orders[oid]['items'].append({
                'detail_id': r['detail_id'],
                'menu_id': r['menu_id'],
                'menu_name': r['menu_name'],
                'image_url': r['image_url'],
                'quantity': r['quantity'],
                'note': r['note'],
            })

        orders_list = list(orders.values())
    except Exception as e:
        flash(f'Error loading orders: {e}')
        orders_list = []

    try:
        cur = db.execute(
            '''
            SELECT t.table_id,
                   t.table_number,
                   t.zone,
                   t.status,
                   COUNT(od.detail_id) AS active_items
            FROM Tables t
            LEFT JOIN Sessions s ON t.table_id = s.table_id
            LEFT JOIN Orders o ON s.session_id = o.session_id AND o.order_status NOT IN ('completed', 'cancelled')
            LEFT JOIN Order_Details od ON o.order_id = od.order_id
            GROUP BY t.table_id
            ORDER BY t.zone, t.table_number
            '''
        )
        tables = cur.fetchall()
    except Exception as e:
        flash(f'Error loading tables: {e}')
        tables = []

    return render_template('index.html', orders=orders_list, tables=tables)


@app.route('/table/<int:table_id>')
def table_orders(table_id):
    db = get_db()
    try:
        table = db.execute('SELECT table_id, table_number, zone, status FROM Tables WHERE table_id=?', (table_id,)).fetchone()
        if table is None:
            flash('ไม่พบโต๊ะที่เลือก')
            return redirect(url_for('index'))

        cur = db.execute(
            '''
            SELECT o.order_id, o.order_time, o.order_status,
                   od.detail_id, od.quantity, od.note,
                   m.menu_id, m.menu_name, m.image_url
            FROM Orders o
            JOIN Order_Details od ON o.order_id = od.order_id
            JOIN Menu m ON od.menu_id = m.menu_id
            JOIN Sessions s ON o.session_id = s.session_id
            WHERE s.table_id = ? AND COALESCE(o.order_status, '') NOT IN ('completed', 'cancelled')
            ORDER BY o.order_time DESC, o.order_id, od.detail_id
            '''
            , (table_id,)
        )
        rows = cur.fetchall()

        orders = {}
        for r in rows:
            oid = r['order_id']
            if oid not in orders:
                orders[oid] = {
                    'order_id': oid,
                    'order_time': r['order_time'],
                    'order_status': r['order_status'],
                    'items': [],
                }
            orders[oid]['items'].append({
                'detail_id': r['detail_id'],
                'menu_id': r['menu_id'],
                'menu_name': r['menu_name'],
                'image_url': r['image_url'],
                'quantity': r['quantity'],
                'note': r['note'],
            })
        orders_list = list(orders.values())
    except Exception as e:
        flash(f'Error loading table orders: {e}')
        return redirect(url_for('index'))

    return render_template('table_orders.html', table=table, orders=orders_list)


@app.route('/menu')
def manage_menu():
    db = get_db()
    try:
        cur = db.execute('SELECT menu_id, menu_name, category, price, image_url FROM Menu ORDER BY menu_id ASC')
        rows = cur.fetchall()
        menus = []
        for r in rows:
            m = dict(r)
            menus.append(m)
    except Exception as e:
        flash(f'Error loading menu: {e}')
        menus = []

    categories = ['เนื้อสัตว์', 'ผัก', 'อาหารทะเล', 'เครื่องดื่ม', 'อื่นๆ']
    return render_template('manage_menu.html', menus=menus, categories=categories)


@app.route('/menu/add', methods=['POST'])
def add_menu():
    name = request.form.get('menu_name', '').strip()
    category = request.form.get('category', '').strip()
    price = request.form.get('price', '').strip()
    image_url = request.form.get('image_url', '').strip()

    if not name or not price:
        flash('กรุณาระบุชื่อเมนูและราคา')
        return redirect(url_for('manage_menu'))

    try:
        price_val = float(price)
    except ValueError:
        flash('ราคาต้องเป็นตัวเลข')
        return redirect(url_for('manage_menu'))

    db = get_db()
    try:
        db.execute('INSERT INTO Menu (menu_name, category, price, image_url) VALUES (?, ?, ?, ?)', (name, category, price_val, image_url))
        db.commit()
        flash('เพิ่มเมนูเรียบร้อย')
    except Exception as e:
        db.rollback()
        flash(f'ข้อผิดพลาดขณะเพิ่มเมนู: {e}')

    return redirect(url_for('manage_menu'))


@app.route('/menu/<int:menu_id>/update', methods=['POST'])
def update_menu(menu_id):
    name = request.form.get('menu_name', '').strip()
    category = request.form.get('category', '').strip()
    price = request.form.get('price', '').strip()
    image_url = request.form.get('image_url', '').strip()

    if not name or not price:
        flash('กรุณาระบุชื่อเมนูและราคา')
        return redirect(url_for('manage_menu'))

    try:
        price_val = float(price)
    except ValueError:
        flash('ราคาต้องเป็นตัวเลข')
        return redirect(url_for('manage_menu'))

    db = get_db()
    try:
        cur = db.execute('UPDATE Menu SET menu_name=?, category=?, price=?, image_url=? WHERE menu_id=?', (name, category, price_val, image_url, menu_id))
        db.commit()
        if cur.rowcount == 0:
            flash('ไม่พบเมนูที่ต้องการแก้ไข')
        else:
            flash('แก้ไขเมนูเรียบร้อย')
    except Exception as e:
        db.rollback()
        flash(f'ข้อผิดพลาดขณะแก้ไขเมนู: {e}')

    return redirect(url_for('manage_menu'))


@app.route('/menu/<int:menu_id>/delete', methods=['POST'])
def delete_menu(menu_id):
    db = get_db()
    try:
        db.execute('DELETE FROM Menu WHERE menu_id=?', (menu_id,))
        db.commit()
        flash('ลบเมนูเรียบร้อย')
    except sqlite3.IntegrityError as e:
        db.rollback()
        flash(f'ไม่สามารถลบเมนูได้ เนื่องจากมีการอ้างอิงจากตารางอื่น: {e}')
    except Exception as e:
        db.rollback()
        flash(f'ข้อผิดพลาดขณะลบเมนู: {e}')

    return redirect(url_for('manage_menu'))


def init_db_schema():
    with app.app_context():
        db = get_db()
        try:
            db.execute('ALTER TABLE Menu ADD COLUMN image_url TEXT')
            db.commit()
        except sqlite3.OperationalError:
            pass

        # ลบข้อความหมายเหตุ "เติมรายการให้ครบ 3 รายการ" ออกจากฐานข้อมูล
        try:
            db.execute("UPDATE Order_Details SET note = REPLACE(note, 'เติมรายการให้ครบ 3 รายการ', '') WHERE note LIKE '%เติมรายการให้ครบ 3 รายการ%'")
            db.commit()
        except Exception:
            pass

        mock_images = {
            1: 'https://i.pinimg.com/1200x/e9/4f/77/e94f77255a216989c36a506ef0696dc8.jpg',
            2: 'https://i.pinimg.com/1200x/56/dd/99/56dd99604615e5fcf8dc80b744a88335.jpg',
            3: 'https://i.pinimg.com/736x/7c/35/86/7c358694509f162fe91a9c5f3dfc70d1.jpg',
            4: 'https://i.pinimg.com/1200x/f5/5a/1a/f55a1aff432c957006486ebfbf1929d9.jpg',
            5: 'https://i.pinimg.com/webp85/736x/c5/39/cc/c539cca798e0a90e0155bd236d4281ec.webp',
            6: 'https://i.pinimg.com/1200x/ca/8b/33/ca8b3311a08f6a6832564b99340cbfa1.jpg',
            7: 'https://i.pinimg.com/736x/01/3a/7d/013a7da575d0dc9e8ba02070ffd08223.jpg',
            8: 'https://i.pinimg.com/1200x/03/2b/ac/032bacc783b6b4a319e6e322181ab259.jpg',
            9: 'https://i.pinimg.com/webp85/736x/5a/21/a1/5a21a1d06dc364cd3ee669bd375af894.webp',
            10: 'https://i.pinimg.com/736x/0d/4d/3f/0d4d3f71fb68717877cb4a6c9e639856.jpg'
        }
        for mid, url in mock_images.items():
            db.execute('UPDATE Menu SET image_url = ? WHERE menu_id = ? AND (image_url IS NULL OR image_url = "")', (url, mid))
        db.commit()

if __name__ == '__main__':
    init_db_schema()
    app.run(debug=True)