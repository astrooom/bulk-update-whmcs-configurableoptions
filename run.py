import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv

load_dotenv()


# -----------------------------------
#### START CONFIGURATION ####
# NOTE: This will ONLY update the pricing for the main currency. Please trigger the update for other currencies manually before exposing the product.


monthly = 1.45
COST_PER_UNIT = {
    'monthly': monthly,
    'quarterly': monthly * 3,  
    'semiannually': monthly * 6,
    'annually': monthly * 10, # 2 months free
    # 'biennially': 9.60,
    # 'triennially': 19.20
}

MAIN_CURRENCY_ID = 1 # Assuming id 1 is the main currency. Can be checked by running: SELECT id, code, `default` FROM tblcurrencies;

# To find the configoptionid, to go the Configurable Option Groups section in WHMCS: https://whmcs.example/admin/configproductoptions.php?action=managegroup&id=1
# Then, click to edit the configurable option in the group you want to set pricing for.
# The configid appears in the URL of the popup window, and looks like this: https://whmcs.example/admin/configproductoptions.php?manageoptions=true&cid=1479 (cid is the configoptionid)
CONFIGOPTION_ID = 1

PRODUCT_ID = 1  # Main product ID

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
      
# def get_main_product_pricing(connection, product_id):
#     """Retrieve main product pricing for all terms."""
#     cursor = connection.cursor()
#     query = """
#     SELECT monthly, quarterly, semiannually, annually, biennially, triennially
#     FROM tblpricing
#     WHERE currency = %s AND relid = %s AND type = 'product'
#     """
#     cursor.execute(query, (MAIN_CURRENCY_ID, product_id))
#     return cursor.fetchone()

def configure(connection, configoptionid, min_value, max_value, unit_type):
    """ Replace existing configoptionssubs with a new range and unit type. """
    try:
        cursor = connection.cursor()
        # Delete existing configoptionssubs for the given configoptionid
        delete_sql = "DELETE FROM tblproductconfigoptionssub WHERE configid = %s"
        cursor.execute(delete_sql, (configoptionid,))            

        # Insert new configoptionssubs and update pricing
        insert_sql = """
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
        VALUES (%s, 'configoptions', LAST_INSERT_ID(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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

            cursor.execute(insert_sql, (configoptionid, option_name, value, hidden))
          
          
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

            final_prices = tuple(periodic_prices) + setup_fees
            

            # Set all the configoption prices
            cursor.execute(update_configoptionsub_pricing_sql, (MAIN_CURRENCY_ID, *final_prices))
            
        # Set the main product prices
        final_main_product_prices = tuple(main_product_price) + setup_fees
        cursor.execute(update_mainproduct_pricing_sql, (*final_main_product_prices, MAIN_CURRENCY_ID, PRODUCT_ID))

        connection.commit()
        print(f"Config options and pricing updated for configoptionid {configoptionid} with range {min_value} to {max_value} {unit_type}.")
    except Error as e:
        print(f"Error: {e}")
        connection.rollback()
        print("Rollback successful")

if __name__ == "__main__":
    connection = connect_to_database()
    if connection and connection.is_connected():
      
        # main_product_pricing = get_main_product_pricing(connection, PRODUCT_ID)
        
        configure(connection, CONFIGOPTION_ID, MIN_VALUE, MAX_VALUE, UNIT_TYPE)
        
        connection.close()
