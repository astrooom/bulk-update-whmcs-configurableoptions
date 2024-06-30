import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv

load_dotenv()


# -----------------------------------
#### START CONFIGURATION ####

monthly = 1.45
COST_PER_UNIT = {
    'monthly': monthly,
    'quarterly': monthly * 3,  
    'semiannually': monthly * 6,
    'annually': monthly * 10, # 2 months free
    # 'biennially': 9.60,
    # 'triennially': 19.20
}

# To find the configoptionid, to go the Configurable Option Groups section in WHMCS: https://whmcs.example/admin/configproductoptions.php?action=managegroup&id=1
# Then, click to edit the configurable option in the group you want to set pricing for.
# The configid appears in the URL of the popup window, and looks like this: https://whmcs.example/admin/configproductoptions.php?manageoptions=true&cid=1479 (cid is the configoptionid)
CONFIGOPTION_ID = 1479

PRODUCT_ID = 56  # Main product ID

MIN_VALUE = 2  # Minimum value
MAX_VALUE = 24  # Maximum value
UNIT_TYPE = "GB"  # Unit type: "GB", or any other unit

#------------------------------------
#### END CONFIGURATION ####


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
      
def get_currency_info(connection):
    cursor = connection.cursor()
    cursor.execute("SELECT id, rate FROM tblcurrencies")
    return cursor.fetchall()  # Returns a list of tuples (id, rate)

def configure(connection, configoptionid, min_value, max_value, unit_type):
    """ Replace existing configoptionssubs with a new range and unit type. """
    try:
        connection.start_transaction()
        
        cursor = connection.cursor()
        
        currency_info = get_currency_info(connection)
        
        # Delete existing configoptionssubs for the given configoptionid
        delete_sql = "DELETE FROM tblproductconfigoptionssub WHERE configid = %s"
        cursor.execute(delete_sql, (configoptionid,))            

        # Insert new configoptionssubs and update pricing
        insert_configoptionssub_sql = """
        INSERT INTO tblproductconfigoptionssub (configid, optionname, sortorder, hidden)
        VALUES (%s, %s, %s, %s)
        """
        
        update_mainproduct_pricing_sql = """
        UPDATE tblpricing
        SET monthly = %s, quarterly = %s, semiannually = %s, annually = %s, biennially = %s, triennially = %s, msetupfee = %s, qsetupfee = %s, ssetupfee = %s, asetupfee = %s, bsetupfee = %s, tsetupfee = %s
        WHERE currency = %s AND relid = %s AND type = 'product'
        """

        update_configoptionsub_pricing_sql = """
        INSERT INTO tblpricing (currency, type, relid, monthly, quarterly, semiannually, annually, biennially, triennially, msetupfee, qsetupfee, ssetupfee, asetupfee, bsetupfee, tsetupfee)
        VALUES (%s, 'configoptions', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        setup_fees = (0,0,0,0,0,0) # Disable setup-fees for now.
        
        main_product_price = []
        
        for value in range(min_value, max_value + 1):
            
            # Set hidden to 1 if the min value is above 1 for all values in between 1 and the min value
            hidden = 0
            # if min_value > 1 and value < min_value:
            #     hidden = 1
                
            #min_value = 1 # Reset to 1 to not mess with the calculation
                
            if unit_type == "GB":
                option_name = f"{value * 1024}|{value}GB"
            else:
                option_name = f"{value}|{value}{unit_type}"

            cursor.execute(insert_configoptionssub_sql, (configoptionid, option_name, value, hidden))
            last_insert_id = cursor.lastrowid  # Used to update the pricing with multiple currencies
          
            periodic_prices = []
            expected_terms = ['monthly', 'quarterly', 'semiannually', 'annually', 'biennially', 'triennially']
            base_costs = {term: min_value * COST_PER_UNIT.get(term, 0) for term in expected_terms}
            for term in expected_terms:
                # Get the cost per unit, defaulting to -1 if not found
                cost = COST_PER_UNIT.get(term, -1)
                if cost == -1:
                    
                    # -1 disables the pricing for this term
                    periodic_prices.append(-1)
                    
                    if value == min_value:
                        main_product_price.append(-1) # Also disable this term on the main product
                    
                    continue
                
                calculated_price = value * cost
                
                if value == min_value:  # Check if it's the first value. If so, set to 0 since we are relying on the pricing of the main product.
                    #print(cost)
                    main_product_price.append(calculated_price)
                    
                    calculated_price = 0
                    
                else:
                    calculated_price -= COST_PER_UNIT[term]
                
                calculated_price = value *  COST_PER_UNIT.get(term, 0) - base_costs[term]
                periodic_prices.append(calculated_price)
                
            # Update the pricing for each currency
            for currency_id, currency_rate in currency_info:
                currency_periodic_prices = [price if price == -1 else price * float(currency_rate) for price in periodic_prices]
                final_prices = tuple(currency_periodic_prices) + setup_fees
                cursor.execute(update_configoptionsub_pricing_sql, (currency_id, last_insert_id, *final_prices))

            
        # Set the main product prices
        for currency_id, currency_rate in currency_info:
            currency_main_product_price = [price if price == -1 else price * float(currency_rate) for price in main_product_price]
            final_main_product_prices = tuple(currency_main_product_price) + setup_fees
            cursor.execute(update_mainproduct_pricing_sql, (*final_main_product_prices, currency_id, PRODUCT_ID))

        connection.commit()
        print(f"Config options and pricing updated for configoptionid {configoptionid} with range {min_value} to {max_value} {unit_type}.")
    except Error as e:
        print(f"Error: {e}")
        connection.rollback()
        print("Rollback successful")

if __name__ == "__main__":
    connection = connect_to_database()
    if connection and connection.is_connected():    
        configure(connection, CONFIGOPTION_ID, MIN_VALUE, MAX_VALUE, UNIT_TYPE)
        connection.close()
