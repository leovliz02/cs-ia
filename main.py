import psycopg2

# Supabase connection info (hardcoded for testing)
USER = "postgres"
PASSWORD = "onetwo34"
HOST = "aws-1-ap-southeast-2.pooler.supabase.com"
PORT = "6543"  
DBNAME = "postgres"

print("Connecting to database with:")
print(USER, PASSWORD, HOST, PORT, DBNAME)

try:
    connection = psycopg2.connect(
        user=USER,
        password=PASSWORD,
        host=HOST,
        port=PORT,
        dbname=DBNAME
    )
    print("Connection successful!")

    # Create a cursor to execute SQL queries
    cursor = connection.cursor()
    
    # Example query
    cursor.execute("SELECT NOW();")
    result = cursor.fetchone()
    print("Current Time:", result)

    # Close the cursor and connection
    cursor.close()
    connection.close()
    print("Connection closed.")

except Exception as e:
    print(f"Failed to connect: {e}")
