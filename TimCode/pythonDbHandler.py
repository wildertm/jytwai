import os, inspect, pickle, MySQLdb

#These two functions store and extract Python pickled dictionaries.
#Code from http://docs.python.org/2/library/pickle.html
def storeClassifier(dictionary, botID = None):
    conn = connect()
    cursor = conn.cursor()
    pickledDatabaseInput = pickle.dumps(dictionary, protocol=1)
    if botID != None:
        cursor.execute('insert into snapshots(classifier, bot_id) values(%s, %s)', (pickledDatabaseInput, botID))       
    else:
        print 'ARRRGHHH'
        sql = "insert into bots(classifier) values(%s)"
        cursor.execute(sql, (pickledDatabaseInput,))
    conn.commit()
    cursor.close()
    conn.close()
    
def loadClassifier(botID):
    conn = connect()
    cursor = conn.cursor()
    query = 'select * from bots where bot_id = %d'% (botID)
    cursor.execute(query)
    blob = cursor.fetchone()
    conn.commit()
    cursor.close()
    conn.close()
    return pickle.loads(blob[2])

def connect():
    conn = MySQLdb.connect(host = "localhost",
                           user = "root",
                           passwd = "test1234",
                           db = "ai")
    return conn

dictionary =  {1:'a', 2:'b', 3:'c'}
storeClassifier(dictionary)
print loadClassifier(54)
