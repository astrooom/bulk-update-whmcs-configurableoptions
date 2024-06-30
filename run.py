import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv

load_dotenv()

# Set the cost per unit (e.g., per GB or per slot)
# NOTE: This will ONLY update the pricing for the main currency. Please trigger the update for other currencies manually before exposing the product.

COST_PER_UNIT = {
    'monthly': 1,
    'quarterly': 1.50,  # Example cost for 3 months
    'semiannually': 2.70,  # Example cost for 6 months
    'annually': 4.80  # Example cost for 12 months
}

MAIN_CURRENCY_ID = 1 # Assuming id 1 is the main currency. Can be checked by running: SELECT id, code, `default` FROM tblcurrencies;

def connect_to_database():
    """ Establish a connection to the database. """
    try:
        connection = mysql.connector.connect(
            host=os.environ.get('DB_HOST'),
            database=os.environ.get('DB_NAME'),
            user=os.environ.get('DB_USER'),
            password=os.environ.get('DB_PASSWORD')
        )
        return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None
      
def get_main_product_pricing(connection, product_id):
    """Retrieve main product pricing for all terms."""
    cursor = connection.cursor()
    query = """
    SELECT monthly, quarterly, semiannually, annually, biennially, triennially
    FROM tblpricing
    WHERE currency = %s AND relid = %s AND type = 'product'
    """
    cursor.execute(query, (MAIN_CURRENCY_ID, product_id))
    return cursor.fetchone()

def replace_configoptionssubs(connection, configoptionid, min_value, max_value, unit_type, main_product_pricing):
    """ Replace existing configoptionssubs with a new range and unit type. """
    try:
        cursor = connection.cursor()
        # Delete existing configoptionssubs for the given configoptionid
        delete_sql = "DELETE FROM tblproductconfigoptionssub WHERE configid = %s"
        cursor.execute(delete_sql, (configoptionid,))

        # Insert new configoptionssubs and update pricing
        insert_sql = """
        INSERT INTO tblproductconfigoptionssub (configid, optionname, sortorder, hidden)
        VALUES (%s, %s, %s, 0)
        """
        update_pricing_sql = """
        INSERT INTO tblpricing (currency, type, relid, monthly, quarterly, semiannually, annually, biennially, triennially, msetupfee, qsetupfee, ssetupfee, asetupfee, bsetupfee, tsetupfee)
        VALUES (%s, 'configoptions', LAST_INSERT_ID(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        first_value = True  # Flag to set the first value's pricings to zero since we are relying on the pricing of the main product.
        
        for value in range(min_value, max_value + 1):
            if unit_type == "GB":
                option_name = f"{value * 1024}|{value}GB"
            else:
                option_name = f"{value}|{value}{unit_type}"

            cursor.execute(insert_sql, (configoptionid, option_name, value))
          
          
            periodic_prices = []
            expected_terms = ['monthly', 'quarterly', 'semiannually', 'annually', 'biennially', 'triennially']
            for term in expected_terms:
                # Get the cost per unit, defaulting to -1 if not found
                cost = COST_PER_UNIT.get(term, -1)
                if cost == -1:
                    # -1 disables the pricing for this term
                    periodic_prices.append(-1)
                    continue
                        
                calculated_price = value * cost                
                if value == min_value:  # Check if it's the first value. If so, set to 0 since we are relying on the pricing of the main product.
                    calculated_price = 0
                else:
                    main_product_price_for_term = float(main_product_pricing[expected_terms.index(term)])
                    calculated_price -= main_product_price_for_term
                
                periodic_prices.append(calculated_price)
        
        
            setup_fees = (0,0,0,0,0,0) # Disable setup-fees for now.

            final_prices = tuple(periodic_prices) + setup_fees

            cursor.execute(update_pricing_sql, (MAIN_CURRENCY_ID, *final_prices))

        connection.commit()
        print(f"Config options and pricing updated for configoptionid {configoptionid} with range {min_value} to {max_value} {unit_type}.")
    except Error as e:
        print(f"Error: {e}")
        connection.rollback()
        print("Rollback successful")

if __name__ == "__main__":
    connection = connect_to_database()
    if connection and connection.is_connected():
      
        # To find the configoptionid, to go the Configurable Option Groups section in WHMCS: https://whmcs.example/admin/configproductoptions.php?action=managegroup&id=1
        # Then, click to edit the configurable option in the group you want to set pricing for.
        # The configid appears in the URL of the popup window, and looks like this: https://whmcs.example/admin/configproductoptions.php?manageoptions=true&cid=1479 (cid is the configoptionid)
        configoptionid = 1479
        
        product_id = 56  # Main product ID
        
        min_value = 1  # Minimum value
        max_value = 24  # Maximum value
        unit_type = "GB"  # Unit type: "GB", or any other unit
        
        main_product_pricing = get_main_product_pricing(connection, product_id)
        print(f"Main product pricing: {main_product_pricing}")
        
        replace_configoptionssubs(connection, configoptionid, min_value, max_value, unit_type, main_product_pricing)
        
        connection.close()
        print("MySQL connection is closed")
