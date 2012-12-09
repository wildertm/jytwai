def attackRegression(instance, bot, action): 
        distanceVector = instance.features['enemyFlag'] - action[2]
        return 10/(distanceVector.length()+3)
def currentActionRegression(instance, bot, action): 
        return 1
def defendRegression(instance, bot, action): 
        distanceVector = instance.features['enemyFlag'] - action[2]
        return 10/(distanceVector.length()+3)      
def chargeRegression(instance, bot, action): 
        distanceVector = instance.features['enemyFlag'] - action[2]
        return 10/(distanceVector.length()+3)    
def moveRegression(instance, bot, action): 
        distanceVector = instance.features['enemyFlag'] - action[2]
        return 10/(distanceVector.length()+3)
def botsInSightCone(instance, bot, action):
        enemybotsseen = 0
        for bot in instance.game.bots_alive:
                VisibleLiveEnemies = [enemybot for enemybot in bot.visibleEnemies if enemybot.health != 0]
                enemybotsseen += len(VisibleLiveEnemies)
                return enemybotsseen
        return 0
