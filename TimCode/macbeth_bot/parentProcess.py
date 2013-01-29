#Twilder
import pythonDbHandler #Manages connecting to our SQL database and retrieving/storing classifier dicts.
#STD
import os
import subprocess
import regressions
import regressions2
import random
import sys
import copy
#KZ
import bootstrap
from api import commands
from aisbx import platform, callstack
from game import application

class genetic():
        def __init__(self):
                self.results = []
                self.mutate_rate = .4
                #How much %change can happen in a feature in one iteration.
                self.mutate_magnitude = 1.0
                self.generations = 0
                self.max_generations = 3
                self.num_bots = 4
                
        def run(self):
            converged = False
            self.pop = self.get_pop()
            
            while converged == False:
                converged = self.one_generation()
                self.generations += 1

            print "DONE WITH %d GENERATIONS" % self.max_generations

        def one_generation(self):
            print
            print "################################### STARTING GENERATION ###################################"
            print
            
            results = self.eval_pop(self.pop)
            print
            print "RESULTS: ", results
            scored_bots = self.score_pop(results, self.pop)
            print
            print "SCORED BOTS: ", scored_bots
            parents, dead_bots = self.get_parents(scored_bots)
            print
            print "PARENTS: ", parents
            print "DEAD_BOTS: ", dead_bots
            offspring = self.get_offspring(parents, dead_bots)
            print
            print "OFFSPRING: "
            self.print_offspring(offspring)
            offspring = self.crossover_offspring(offspring)
            print
            print "CROSSOVER OFFSPRING: "
            self.print_offspring(offspring)
            offspring = self.mutate_offspring(offspring)
            print
            print "MUTATED OFFSPRING: "
            self.print_offspring(offspring)
            self.replace_pop1_with_pop2(offspring)
            print
            print "DONE WITH GENERATION"
            return self.evaluate_pop_to_see_if_good_enough(offspring)

        def print_offspring(self, offspring):
            for pair in offspring:
                bot_id, classifier = pair
                print "CLASSIFIER FOR BOT %s" % str(bot_id)
                for command in classifier.keys():
                    print "\t", command
                    for regression in classifier[command]:
                        print "\t\tREGRESSION: ", regression[0],"    WEIGHT: ", regression[1]

        def get_pop(self):
            bot_ids = make_bots(self.num_bots)
            return bot_ids

        def eval_pop(self, bot_id_list):
            num_games = len(bot_id_list)/2
            results = run_full_trial(num_games, 1, bot_id_list)
            return results
            
        def score_pop(self, results, pop):
            #Processes long list of lists of form: [redID, red_score, map_played]
            #Tally the score differential for our bots across all games.
            scored_bots = {}
            for bot_id in pop:
                scored_bots[bot_id] = 0.0
            for result in results:
                bot_id = result[0]
                points_scored = result[1][0]
                points_given_up = result[1][1]
                scored_bots[bot_id] += points_scored - points_given_up
            return scored_bots
                   
        def get_parents(self, scored_bots):
            sortable_bots = []
            for bot_id in scored_bots.keys():
                sortable_bots.append((scored_bots[bot_id], bot_id))
                sortable_bots.sort()

            #Top half of field lives.
            parent_tuples = sortable_bots[len(sortable_bots)/2:]
            parents = {}
            for score, parent_id in parent_tuples:
                parents[parent_id] = score

            dead_bots = [bot for bot in scored_bots.keys() if bot not in parents.keys()]
            return parents, dead_bots

        
        def get_offspring(self, parents, dead_bots):
            offspring = []
            for parent in parents.keys():
                classifier = pythonDbHandler.loadClassifier(parent)
                offspring.append((parent, copy.deepcopy(classifier)))
                #Replace the dead bot's classifiers with the living one at a time.
                bot_to_be_overwritten = dead_bots.pop()
                offspring.append((bot_to_be_overwritten, copy.deepcopy(classifier)))
            return offspring

        def crossover_offspring(self, offspring):
            return offspring
            
        def mutate_offspring(self, offspring):
            for bot_id, classifier in offspring:
                for command_type in classifier.keys():
                    for regression in classifier[command_type]:
                        if self.mutate_rate < random.random():
                            regression[1] += regression[1]*random.uniform(-self.mutate_magnitude, self.mutate_magnitude)
            return offspring
            
        def replace_pop1_with_pop2(self, offspring):
            for bot_id, classifier in offspring:
                pythonDbHandler.storeClassifier(classifier, botID = bot_id)
            
        def evaluate_pop_to_see_if_good_enough(self, offspring):
            if self.generations >= self.max_generations:
                return True
            else:
                return False

                

def get_classifier():
        classifier = {commands.Charge: [[regressions2.popular_ground, 9.650258890144737e-05],
            [regressions2.go_to_flank_brink, 0.5168413499641142],
            [regressions2.spread_targets2, 3.135546964219316],
            [regressions2.go_toward_flag, 7.385730487197322],
            [regressions2.distance, 0.008742592941517344],
            [regressions2.enemy_distance, 6.1823582490990034],
            [regressions2.time_to_score, 404.9049154509292]],

            commands.Attack: [[regressions2.popular_ground, 0.001035764358563072],
            [regressions2.go_to_flank_brink, 0.01010428860477668],
            [regressions2.spread_targets2, 0.00015682277681588162],
            [regressions2.go_toward_flag, 0.03999221454195154],
            [regressions2.distance, 0.12026976410187865],
            [regressions2.enemy_distance, 0.005690750199340896],
            [regressions2.time_to_score, 3549.0439906214983]],

            commands.Move : [],
            commands.Defend : []
            }
        return classifier

#Starts numGames games using numGamesx2 auto generated bot classifiers based on the default classifier.
def spawn_trial_bots(num_bots):
        botIDlist = []
        defaultClassifier = get_classifier()
        for x in range(num_bots):
                pythonDbHandler.storeClassifier(defaultClassifier)
        maximum = pythonDbHandler.getLargestBotID()
        for x in range(num_bots):
                botIDlist.append(maximum)
                maximum -= 1
        print 'Initial botIDlist: ', botIDlist
        return botIDlist

def spawn_trial_bots2(numGames):
        botIDlist = []
        for x in range(10):
                botIDlist.append(x)
        return botIDlist

def run(level = "map22", commanders = ["mycmd.macbethCommander", "mycmd.macbethCommander"]):
    try:
        sys.stderr.write('.')
        runner = platform.ConsoleRunner()
        runner.accelerate()
        app = application.CaptureTheFlag(commanders, level, quiet = True, games = 1)
        runner.run(app)
        sys.stderr.write('o')
        return level, app.scores
    except Exception as e:
        print >> sys.stderr, str(e)
        tb_list = callstack.format(sys.exc_info()[2])
        for s in tb_list:
            print >> sys.stderr, s
        raise
    except KeyboardInterrupt:
        return None 
                
def run_trial_round(botIDlist):
        print 'Running trial round.'
        trialIDlist = botIDlist[:]
        random.shuffle(trialIDlist)
        maximum = max(botIDlist)
        numGames = len(botIDlist)/2

        levels = ['map11']
        commander1 = "mycmd.macbethCommander"
                
        results = []
        game = 0
        for x in range(numGames):
                #Run a game
                redID = trialIDlist.pop()
                os.environ['red_team_bot_id'] = str(redID)
                blueID = trialIDlist.pop()
                os.environ['blue_team_bot_id'] =  str(blueID)
                test_level = random.sample(levels, 1)[0]
                competitors = [commander1, commander1]
                result = run(level = test_level, commanders = competitors)

                #Store the results
                map_played = result[0]
                blue_score = result[1][('Blue', "macbethCommander")]
                red_score = result[1][('Red', "macbethCommander")]
                results.append([blueID, blue_score, map_played])
                results.append([redID, red_score, map_played])
        return results

def run_full_trial(num_games, num_iterations, botIDlist):
        print 'BOT IDS TO BE TESTED: ', botIDlist
        mega_results = []
        for x in range(num_iterations):
                results = run_trial_round(botIDlist)
                for item in results:
                        mega_results.append(item)
        return mega_results

def make_bots(num_bots):
        botIDlist = spawn_trial_bots(num_bots)
        return botIDlist

if __name__ == "__main__":
    TEST = False
    genetic_container = genetic()
    if not TEST:
        genetic_container.run()
    else:
        assert(genetic_container.score_pop([[6, [1, 1], 'map11'], [5, [1, 1], 'map11']], [5,6]) == {5: 0.0, 6: 0.0})
        assert(genetic_container.get_parents({5: -1.0, 6: 1.0, 7:8.0, 8:-8.0}) == ({6: 1.0, 7: 8.0}, [8, 5]))
        assert(len(genetic_container.get_offspring({6: 1.0, 7: 8.0}, [8, 5])) == 4)
        classifier = get_classifier()
        offspring = [(1, copy.deepcopy(classifier)), (2, copy.deepcopy(classifier))]
        assert(type(genetic_container.mutate_offspring(offspring)) == list)
        
        
        
        

                
