import mysql.connector

# Database Connection
conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Karthik@2004",
    database="farmdirect"
)

cursor = conn.cursor()

# Create Tables
cursor.execute("""
CREATE TABLE IF NOT EXISTS products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100),
    price DECIMAL(10,2),
    quantity INT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    customer_name VARCHAR(100),
    product_name VARCHAR(100),
    quantity INT
)
""")

conn.commit()


def main_menu():
    print("\n===== FARMER MARKET =====")
    print("1. Add Product")
    print("2. View Products")
    print("3. Place Order")
    print("4. View Orders")
    print("5. Delete Product")
    print("6. Exit")


def add_product():
    name = input("Enter product name: ")
    price = float(input("Enter price per kg: "))
    quantity = int(input("Enter quantity: "))

    sql = "INSERT INTO products(name, price, quantity) VALUES(%s,%s,%s)"
    values = (name, price, quantity)

    cursor.execute(sql, values)
    conn.commit()

    print("✅ Product added successfully!")


def view_products():
    cursor.execute("SELECT * FROM products")
    products = cursor.fetchall()

    print("\n===== PRODUCTS =====")
    for product in products:
        print(product)


def place_order():
    customer = input("Customer name: ")
    product = input("Product name: ")
    qty = int(input("Quantity: "))

    sql = """
    INSERT INTO orders(customer_name, product_name, quantity)
    VALUES(%s,%s,%s)
    """

    cursor.execute(sql, (customer, product, qty))
    conn.commit()

    print("✅ Order placed successfully!")


def view_orders():
    cursor.execute("SELECT * FROM orders")
    orders = cursor.fetchall()

    print("\n===== ORDERS =====")
    for order in orders:
        print(order)


def delete_product():
    pid = int(input("Enter Product ID to delete: "))

    cursor.execute("DELETE FROM products WHERE id=%s", (pid,))
    conn.commit()

    print("✅ Product deleted successfully!")


while True:
    main_menu()

    choice = input("Enter choice: ")

    if choice == "1":
        add_product()

    elif choice == "2":
        view_products()

    elif choice == "3":
        place_order()

    elif choice == "4":
        view_orders()

    elif choice == "5":
        delete_product()

    elif choice == "6":
        print("Thank You!")
        break

    else:
        print("❌ Invalid Choice")

conn.close()