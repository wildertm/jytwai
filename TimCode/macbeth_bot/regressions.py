import math
from api import vector2, commands
import visibility

def currentActionRegression(instance, bot, command):
    return 1

def enemyFlag(instance, bot, command):
    distanceVector = instance.game.enemyTeam.flag.position - command.target[0]
    return 2/(distanceVector.length()+1)    

def timeToScore(instance, bot, command):
    if bot.flag != None:
        destination = instance.game.team.flagScoreLocation
        distanceVector = command.target[0] - destination
        return -5*(distanceVector.length()+1)
    else:
        return 0

def botsInSightCone(instance, bot, command):
    enemybotsseen = 0
    for bot in instance.game.bots_alive:
            VisibleLiveEnemies = [enemybot for enemybot in bot.visibleEnemies if enemybot.health != 0]
            enemybotsseen += len(VisibleLiveEnemies)
            return enemybotsseen
    return 0

def canEnemyBotSeePath(instance, bot, command):
    enemyRange = instance.level.firingDistance
    ourDestination = command.target[0]
    #TODO improve to a path.
    points = visibility.line(bot.position, ourDestination)
    for enemyBot in instance.game.enemyTeam.members:
        count = 0
        for point in points:
            if count%7 == 0 and sightCheck2(instance, enemyBot, point) == True:
                print 'THEY SEE'
                return 1
    return 0

def spread(instance, bot, command):
    totalDistance = 0
    for friendly in instance.game.team.members:
        totalDistance += (friendly.position - bot.position).length()
    return totalDistance/10

def lookTowardEnemyBots(instance, bot, command):
    totalAngle = 0.0
    if type(command) == commands.Attack:
        lookAtVector = command.lookAt
        relativeLookAtVector = lookAtVector - bot.position
        for enemyBot in instance.game.enemyTeam.members:
            if enemyBot.seenlast != None and enemyBot.health > 0:
                seperationVector = bot.position - enemyBot.position
                angle = getAngle(seperationVector, relativeLookAtVector)
                totalAngle += 2*angle/(enemyBot.seenlast + 10)
    elif type(command) == commands.Defend:
        defendLookVector = command.facingDirection
        for enemyBot in instance.game.enemyTeam.members:
            if enemyBot.seenlast != None and enemyBot.health > 0:
                seperationVector = bot.position - enemyBot.position
                angle = getAngle(seperationVector, defendLookVector)
                totalAngle += 2*angle/(enemyBot.seenlast + 10)
    return totalAngle

def lookTowardEnemyBase(instance, bot, command):
    angle = 0.0
    enemySpawn = instance.game.enemyTeam.botSpawnArea[0]    
    if type(command) == commands.Attack:
        lookAtVector = command.lookAt
        relativeLookAtVector = lookAtVector - bot.position
        enemyBaseVector = enemySpawn - bot.position
        angle = getAngle(enemyBaseVector, relativeLookAtVector)
    elif type(command) == commands.Defend:
        defendLookVector = command.facingDirection
        seperationVector = bot.position - enemyBot.position
        angle = getAngle(seperationVector, defendLookVector)
    return angle
        

#########################
## Utility Functions   ##
#########################

#TODO add walls blocking enemy sight. 
def sightCheck(instance, enemyBot, point):
    if enemyBot.seenlast != None and enemyBot.health > 0 and enemyBot.seenlast < 3:
            viewVector = instance.level.firingDistance * enemyBot.facingDirection
            #Vector from our bot's destination to enemy bot.
            destinationVector = enemyBot.position - point
            if getAngle(destinationVector, viewVector) < instance.level.fieldOfViewAngles[enemyBot.state]/2:
                if destinationVector.length < instance.level.firingDistance:
                    return True
    else:
        return False

def sightCheck2(instance, enemyBot, point):
    if enemyBot.position != None:
        visible_cells = visibleSquares(instance, enemyBot.position)
        pointToEnemyVector = point = enemyBot.position
        if point in visible_cells and getAngle(pointToEnemyVector, enemy.facingdirection) < instance.level.fieldOfViewAngles[enemyBot.state]/2:
            return True
        else:
            return False
    else:
        return False
    
def visibleSquares(instance, viewing_point):
    visible_cell_list = []
    w = visibility.Wave((88, 50), lambda x, y: instance.level.blockHeights[x][y] > 1, lambda x, y: visible_cell_list.append((x,y)))
    w.compute(viewing_point)
    return visible_cell_list

def getAngle(vectorA, vectorB):
    return math.acos(vectorA.dotProduct(vectorB)/(vectorA.length()*vectorB.length()))
