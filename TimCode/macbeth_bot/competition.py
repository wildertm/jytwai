import bootstrap
import sys
import os

from multiprocessing.queues import Queue
from multiprocessing.pool import Pool
import multiprocessing
import itertools

from aisbx import platform, callstack
from game import application

def genetic():
    converged = False
    get_pop()
    while converged == False:
        eval_pop()
        score_pop()
        get_parents()
        get_offspring()
        crossover_offspring()
        mutate_offspring()
        replace_pop1_with_pop2()
        evaluate_pop_to_see_if_good_enough()

def get_pop():
    pass

def eval_pop():
    competition()
    
def score_pop():
    pass
    
def get_parents():
    pass
    
def get_offspring():
    pass

def crossover_offspring():
    pass
    
def mutate_offspring():
    pass
    
def replace_pop1_with_pop2():
    pass
    
def evaluate_pop_to_see_if_good_enough():
    pass



def run(args):
    try:
        level, commanders = args
        sys.stderr.write('.')
        runner = platform.ConsoleRunner()
        runner.accelerate()
        app = application.CaptureTheFlag(list(commanders), level, quiet = True, games = 1)
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


def competition():
    p = Pool(processes = 4)

    total = 0
    scores = {}

    mycmd = 'examples.Greedy'
    competitors = ['examples.Greedy']
    levels = ['map00']

    pairs = itertools.product([mycmd], competitors)
    games = list(itertools.product(levels, pairs))
    
    print "Running against %i commanders on %i levels, for a total of %i games.\n" % (len(competitors), len(levels), len(games))
    try:
        for level, results in p.map(run, games):
            for (_, bot), score in results.items():
                scores.setdefault(bot, [0, 0, 0, 0, 0])
                scores[bot][0] += score[0]                      # Flags captured.
                scores[bot][1] += score[1]                      # Flags conceded.
                scores[bot][2] += int(score[0] > score[1])      # Win.
                scores[bot][3] += int(score[0] == score[1])     # Draw.
                scores[bot][4] += int(score[1] > score[0])      # Loss.
            total += 1
    except KeyboardInterrupt:
        print "\nTerminating competition due to keyboard interrupt."
        p.terminate()
        p.join()
    else:        
        print "\n"
        for r, s in sorted(scores.items(), key = lambda i: i[1][2]*30 + i[1][3]*10 + i[1][0] - i[1][1], reverse = True):
            nick = r.replace('Commander', '')
            if nick in mycmd: continue

            print "{}\n\tCaptured {} flags and conceded {}.\n\tWon {}, drew {} and lost {}.\n".format(nick.upper(), *s)

        print '\n\nAll matches played against {}; best opponent at top of list.\n'.format(mycmd)
        
if __name__ == "__main__":
    competition()
