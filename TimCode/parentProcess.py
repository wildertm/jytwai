import pythonDbHandler #Manages connecting to our SQL database and retrieving/storing classifier dicts.
import os, subprocess
from api import commands
import regressions
import random

def enemyFlag(instance, bot, action):
        if action != 'currentAction':
            vector = action[2] - instance.game.enemyTeam.flag.position
            return -1*vector.length()
        else:
            return 1

def getClassifier():
        classifier = {
        commands.Attack : [[regressions.attackRegression, 1],
                           [regressions.botsInSightCone, 1],
                           ],
        'currentAction' : [[regressions.currentActionRegression, 1],
                           [regressions.botsInSightCone, 1]
                           ],
        commands.Charge : [[regressions.chargeRegression, 1],
                           [regressions.botsInSightCone, 1],
                           ],
        commands.Move :  [[regressions.moveRegression, 1],
                         [regressions.botsInSightCone, 1],
                          ],
        commands.Defend : [[regressions.defendRegression, 1],
                           [regressions.botsInSightCone, 1],
                          ]
                      }
        return classifier

#Starts numGames games using numGamesx2 auto generated bot classifiers based on the default classifier.
def spawnTrialBots(numGames):
        botIDlist = []
        defaultClassifier = getClassifier()
        for x in range(numGames):
                pythonDbHandler.storeClassifier(defaultClassifier)
                pythonDbHandler.storeClassifier(defaultClassifier)
        maximum = pythonDbHandler.getLargestBotID()
        for x in range(numGames):
                botIDlist.append(maximum)
                maximum -= 1
                botIDlist.append(maximum)
                maximum -= 1
        print 'Initial botIDlist: ',botIDlist
        return botIDlist
                
def runTrialRound(botIDlist):
        print 'Running trial round.'
        trialIDlist = botIDlist[:]
        random.shuffle(trialIDlist)
        maximum = max(botIDlist)
        numGames = len(botIDlist)/2
        for x in range(numGames):
                redID = trialIDlist.pop()
                os.environ['red_team_bot_id'] = str(redID)
                blueID = trialIDlist.pop()
                os.environ['blue_team_bot_id'] =  str(blueID)
                p = subprocess.Popen(['python', 'simulate.py', '-c'])                

def runFullTrial(numGames, numIterations):
        botIDlist = spawnTrialBots(numGames)
        print 'BOT IDS TO BE TESTED: ', botIDlist
        for x in range(numIterations):
                runTrialRound(botIDlist)

runFullTrial(1, 1)
        

                
