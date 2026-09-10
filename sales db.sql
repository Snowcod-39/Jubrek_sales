CREATE TABLE admins(
id BIGINT GENERATED ALWAYS AS IDENTITY 
PRIMARY KEY,

full_name VARCHAR(150)NOT NULL,
username Varchar(100)NOT NULL UNIQUE,
password_hash TEXT NOT NULL,

status VARCHAR(20)NOT NULL DEFAULT 'ACTIVE',

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

CONSTRAINT admin_status_check
CHECK(status IN('ACTIVE','INACTIVE...'))
);


CREATE TABLE employees(
id BIGINT GENERATED ALWAYS AS IDENTITY
PRIMARY KEY,

full_name VARCHAR(150) NOT NULL,
username VARCHAR(100) NOT NULL UNIQUE,
password_hash TEXT NOT NULL,
 
status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',

created_at TIMESTAMP NOT NULL DEFAULT
CURRENT_TIMESTAMP,
updated_at TIMESTAMP NOT NULL DEFAULT
CURRENT_TIMESTAMP,

CONSTRAINT employee_status_check
CHECK (status IN('ACTIVE','INACTIVE'))
);


CREATE TABLE categories(
id BIGINT GENERATED ALWAYS AS IDENTITY
PRIMARY KEY,

category_name VARCHAR(100)NOT NULL UNIQUE,

status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

CONSTRAINT categories_status_check
CHECK(status IN('ACTIVE','INACTIVE'))
);


CREATE TABLE products(
id BIGINT GENERATED ALWAYS AS IDENTITY
PRIMARY KEY,

product_name VARCHAR(150)NOT NULL,
category_id BIGINT NOT NULL,
buying_price NUMERIC(12,2) NOT NULL,
selling_price NUMERIC(12,2) NOT NULL,
quantity NUMERIC(12,3) NOT NULL DEFAULT 0,
minimum_stock NUMERIC(12,3) NOT NULL DEFAULT 0,

status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

CONSTRAINT products_category_fk
FOREIGN KEY (category_id)
REFERENCES categories(id)
ON DELETE RESTRICT,

CONSTRAINT products_buying_price_check
CHECK (buying_price >= 0),

CONSTRAINT products_selling_price_check
CHECK (selling_price >= 0),

CONSTRAINT products_quantity_check
CHECK (quantity >= 0),

CONSTRAINT products_minimum_stock_check
CHECK (minimum_stock >= 0),

CONSTRAINT products_status_check
CHECK(status IN('ACTIVE','INACTIVE'))
);

CREATE TABLE receipt_books(
id BIGINT GENERATED ALWAYS AS IDENTITY
PRIMARY KEY,

book_number INTEGER NOT NULL,
book_year INTEGER NOT NULL,
start_number INTEGER NOT NULL,
end_number INTEGER NOT NULL,
number_width INTEGER NOT NULL DEFAULT 4,

started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
ended_at TIMESTAMP,

status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

CONSTRAINT receipt_books_number_check
CHECK (start_number >= 0 AND end_number >= start_number),

CONSTRAINT receipt_books_width_check
CHECK (number_width BETWEEN 1 AND 10),

CONSTRAINT receipt_books_status_check
CHECK(status IN('ACTIVE', 'COMPLETED', 'CANCELLED')),

CONSTRAINT receipt_books_unique_book
UNIQUE(book_year,book_number)
);


CREATE TABLE orders(
id BIGINT GENERATED ALWAYS AS IDENTITY
PRIMARY KEY,

customer_name VARCHAR(150) NOT NULL,
customer_contact VARCHAR(50),

status VARCHAR(20)NOT NULL DEFAULT 'PENDING',

total_amount NUMERIC(12,3)NOT NULL DEFAULT 0,

processed_by BIGINT,

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

CONSTRAINT orders_status_check
CHECK(status IN('PENDING', 'PROCESSING',
'COMPLETED', 'CANCELLED', 'REJECTED')),

CONSTRAINT orders_total_check
CHECK(total_amount >= 0),

CONSTRAINT orders_employee_fk
FOREIGN KEY(processed_by)
REFERENCES employees(id)
ON DELETE RESTRICT
);


CREATE TABLE order_items(
id BIGINT GENERATED ALWAYS AS IDENTITY
PRIMARY KEY,

order_id BIGINT NOT NULL,
product_id BIGINT NOT NULL,
quantity NUMERIC(12,3) NOT NULL,
unit_price NUMERIC(12,3) NOT NULL,
subtotal Numeric(12,3) NOT NULL,

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

CONSTRAINT order_items_order_fk
FOREIGN KEY (order_id)
REFERENCES orders(id)
ON DELETE CASCADE,

CONSTRAINT order_items_product_fk
FOREIGN KEY (product_id)
REFERENCES products(id)
ON DELETE RESTRICT,

CONSTRAINT order_items_unit_price_check
CHECK (unit_price >= 0),

CONSTRAINT order_items_subtotal_check
CHECK (subtotal >= 0)
);


CREATE TABLE sales(
id BIGINT GENERATED ALWAYS AS IDENTITY
PRIMARY KEY,

employee_id BIGINT NOT NULL,
receipt_book_id BIGINT NOT NULL,
receipt_number INTEGER NOT NULL,
order_id BIGINT,

total_amount NUMERIC(12,2) NOT NULL DEFAULT 0,

payment_method VARCHAR(20) NOT NULL DEFAULT 'CASH',
payment_status VARCHAR(20) NOT NULL DEFAULT 'PAID',

sale_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

CONSTRAINT sales_employee_fk
FOREIGN KEY (employee_id)
REFERENCES employees(id)
ON DELETE RESTRICT,

CONSTRAINT sales_receipt_book_fk
FOREIGN KEY (receipt_book_id)
REFERENCES receipt_books(id)
ON DELETE RESTRICT,

CONSTRAINT sales_order_fk
FOREIGN KEY (order_id)
REFERENCES orders(id)
ON DELETE RESTRICT,

CONSTRAINT sales_receipt_unique
UNIQUE(receipt_book_id,receipt_number),

CONSTRAINT sales_receipt_number_check
CHECK(receipt_number >= 0),

CONSTRAINT sales_total_check
CHECK(total_amount >= 0),

CONSTRAINT sales_payment_method_check
CHECK(payment_method IN('CASH','MPESA')),

CONSTRAINT sales_payment_status_check
CHECK(payment_status IN('PAID','PENDING','FAILED'))
);

CREATE TABLE sale_items(
id BIGINT GENERATED ALWAYS AS IDENTITY
PRIMARY KEY,

sale_id BIGINT NOT NULL,
product_id BIGINT NOT NULL,
quantity NUMERIC(12,3) NOT NULL,
selling_price NUMERIC (12,2) NOT NULL,
buying_price NUMERIC(12,2) NOT NULL,
subtotal NUMERIC(12,2) NOT NULL,

CONSTRAINT sale_items_sales_fk
FOREIGN KEY (sale_id)
REFERENCES sales(id)
ON DELETE CASCADE,

CONSTRAINT sale_items_product_fk
FOREIGN KEY (product_id)
REFERENCES products(id)
ON DELETE RESTRICT,

CONSTRAINT sale_items_quantity_check
CHECK (quantity > 0),

CONSTRAINT sale_items_selling_price_check
CHECK (selling_price >= 0),

CONSTRAINT sale_items_buying_price_check
CHECK (buying_price >= 0),

CONSTRAINT sale_price_subtotal_check
CHECK (subtotal >= 0)
);


CREATE TABLE stock_transactions(
id BIGINT GENERATED ALWAYS AS IDENTITY
PRIMARY KEY,

product_id BIGINT NOT NULL,
employee_id BIGINT NOT NULL,
transaction_type VARCHAR(20) NOT NULL,
quantity NUMERIC(12,3)NOT NULL,
previous_quantity NUMERIC(12,3) NOT NULL,
new_quantity NUMERIC(12,3) NOT NULL,
reason TEXT,

transaction_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

CONSTRAINT stock_transactions_product_fk
FOREIGN KEY (product_id)
REFERENCES products(id)
ON DELETE RESTRICT,

CONSTRAINT stock_transactions_employee_fk
FOREIGN KEY (employee_id)
REFERENCES employees(id)
ON DELETE RESTRICT,

CONSTRAINT stock_transactions_type_check
CHECK (transaction_type IN ('STOCK_IN', 'SALE',
'STOCK_REMOVAL', 'STOCK_ADJUSTMENT')),

CONSTRAINT stock_transactions_quantity_check
CHECK (quantity >= 0),

CONSTRAINT stock_transactions_previous_check
CHECK (previous_quantity >= 0),

CONSTRAINT stock_transactions_new_check
CHECK (new_quantity >= 0)
);

CREATE TABLE expenses(
id BIGINT GENERATED ALWAYS AS IDENTITY
PRIMARY KEY,

description VARCHAR(255) NOT NULL,
amount NUMERIC(12,2)NOT NULL,
expense_date DATE NOT NULL DEFAULT CURRENT_DATE,
created_by_admin_id BIGINT,
created_by_employee_id BIGINT,

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

CONSTRAINT expenses_admin_fk
FOREIGN KEY(created_by_admin_id)
REFERENCES admins(id)
ON DELETE RESTRICT,

CONSTRAINT expenses_employee_fk
FOREIGN KEY(created_by_employee_id)
REFERENCES employees(id)
ON DELETE RESTRICT,

CONSTRAINT expenses_amount_check
CHECK (amount >= 0),

CONSTRAINT expenses_creator_check
CHECK ((created_by_admin_id IS NOT NULL AND 
created_by_employee_id IS NULL)
OR
(created_by_admin_id IS NULL AND 
created_by_employee_id IS NOT NULL))
);

ALTER TABLE sales
ADD COLUMN delivery_status VARCHAR(20) NOT NULL DEFAULT
'NOT RELEASED';

ALTER TABLE sales
ADD CONSTRAINT sales_delivery_status_check
CHECK (delivery_status IN('RELEASED', 'NOR RELEASED'))