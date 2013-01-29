import os, inspect, pickle, MySQLdb

def getLargestBotID():
    conn = connect()
    cursor =  conn.cursor()
    cursor.execute("SELECT max(bot_id) from bots")
    result = cursor.fetchone()
    return int(result[0])  

#These two functions store and extract Python pickled dictionaries in the DB.
def storeClassifier(dictionary, botID = None):
    conn = connect()
    cursor = conn.cursor()
    pickledDatabaseInput = pickle.dumps(dictionary, protocol=1)
    if botID != None:
        cursor.execute('update bots SET in_use=FALSE, classifier=%s WHERE bot_id=%s', (pickledDatabaseInput, botID,))       
    else:
        sql = "INSERT INTO bots(classifier, in_use) VALUES(%s, FALSE)"
        cursor.execute(sql, (pickledDatabaseInput,))
    conn.commit()
    cursor.close()
    conn.close()
    
def loadClassifier(botID):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute('select * from bots where bot_id = %d'% (botID,))
    blob = cursor.fetchone()
    cursor.close()
    conn.close()
    return pickle.loads(blob[2])

def connect():
    conn = MySQLdb.connect(host = "localhost",
                           user = "root",
                           passwd = "test1234",
                           db = "ai")
    return conn
