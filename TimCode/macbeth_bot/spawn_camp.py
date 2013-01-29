import math
import itertools
import random
import copy


#Third party modules
import networkx as nx

#KILLZONE modules
from api import vector2, Vector2, commands
import visibility
#Twilder
import enemy_belief
import regressions2

def calculate_spawn_camp(instance):
    initialize_graph(instance)
    exit_paths = get_exit_paths(instance)
    put_exit_paths_in_graph(instance, exit_paths)
    
    close_nodes = get_close_nodes(instance)
    close_nodes = remove_spawn_nodes(instance, close_nodes)
    weight_target_nodes(instance, close_nodes)

    best_targets = get_best_targets(instance, close_nodes)
    instance.choke_dict, instance.master_chokes = get_chokes(instance, best_targets)
    
    weight_camp_locations_by_sight(instance, close_nodes)
    weight_camp_locations_by_base_exposure(instance)
    weight_camp_locations_by_choke_exposure(instance)
    best_positions = produce_best_camp_locations(instance, close_nodes)
    

    return best_positions

def get_best_targets(instance, close_nodes):
    targets = []
    for node in close_nodes:
        if node != 0 and node != None:
            targets.append((instance.graph.node[node]["camp_target"], node))
    targets.sort()
    best_targets = targets[len(targets)-250:]
    return_targets = []
    for score, node in best_targets:
        return_targets.append(node)
    return return_targets

#LEFT OFF - USE Chokes to smartly camp.
def get_chokes(instance, choke_candidates):
    #prevent writing over base space.
    used_set = set()
    start, finish = instance.level.botSpawnAreas[instance.game.enemyTeam.name]
    for i, j in itertools.product(range(int(start.x), int(finish.x)), range(int(start.y), int(finish.y))):
        node_index = regressions2.get_node_index(instance, Vector2(i,j))
        used_set.add(node_index)
            
    choke_dict = {}
    master_chokes = set()
    flag_node = regressions2.get_node_index(instance, instance.game.team.flag.position)
    spawn_node = regressions2.get_node_index(instance, get_enemy_base(instance))

    shortest_length = nx.shortest_path_length(instance.graph, source=spawn_node, target=flag_node, weight="choke_covered")
    choke_count = 0
    while shortest_length == 0.0:
        if len(choke_candidates) == 0.0:
            print "RAN OUT OF CANDIDATES!"
            break
        
        choke_count += 1
        
        one_choke = set()
        choke_center = choke_candidates.pop()
        choke_vector = regressions2.get_node_vector(instance, choke_center)
        
        #Ignore potential chokes too far from their spawn.
        while (choke_vector.distance((get_enemy_base(instance))) > 5.0 or choke_center in used_set) and len(choke_candidates) > 0:
            choke_vector = regressions2.get_node_vector(instance, choke_center)
            choke_center = choke_candidates.pop()
        if len(choke_candidates) == 0:
            print "RAN OUT OF CANDIDATES!"
            return choke_dict, master_chokes
        if choke_vector.distance((get_enemy_base(instance))) > 5.0:
            print "RAN OUT OF CANDIDATES, LAST CANDIDATE DIDN'T WORK!"
            return choke_dict, master_chokes
    
        one_choke.add(choke_center)
        for x in range(4):
            neighbors = set()
            for node in one_choke:
                neighbors2 = instance.graph.neighbors(node)
                if neighbors2 is not None:
                    for neighbor2 in neighbors2:
                        if neighbor2 not in used_set:
                            neighbors.add(neighbor2)
            one_choke = one_choke.union(neighbors)
            used_set = used_set.union(one_choke)
        for node in one_choke:
            instance.graph.node[node]["choke_covered"] = 1.0
            neighbors = instance.graph.neighbors(node)
            for neighbor in neighbors:
                instance.graph.edge[node][neighbor]["choke_covered"] = 1.0
        choke_dict[choke_center] = { "nodes": one_choke, "redundancy": 0}
        master_chokes = master_chokes.union(one_choke)
        shortest_length = nx.shortest_path_length(instance.graph, source=spawn_node, target=flag_node, weight="choke_covered")
        
    return choke_dict, master_chokes

def initialize_graph(instance):
    #Set ambush dictionary.
    for node_index in instance.graph.nodes():
        instance.graph.node[node_index]["exit_path"] = 0.0
        instance.graph.node[node_index]["camp_target"] = 0.0
        instance.graph.node[node_index]["camp_location"] = 0.0
        instance.graph.node[node_index]["choke_covered"] = 0.0

    for edge in instance.graph.edges():
        start = edge[0]
        end = edge[1]
        instance.graph.edge[edge[0]][edge[1]]["choke_covered"] = 0.0

def get_exit_paths(instance):
    start, finish = instance.level.botSpawnAreas[instance.game.enemyTeam.name]
    enemy_base = Vector2(start.x, start.y)
    instance.graph.add_node("enemy_base", position = (start.x, start.y), weight = 0.0)
    instance.graph.node["enemy_base"]["exit_path"] = 0.0
    instance.graph.node["enemy_base"]["camp_target"] = 0.0
    instance.graph.node["enemy_base"]["camp_location"] = 0.0
        
    for i, j in itertools.product(range(int(start.x), int(finish.x)), range(int(start.y), int(finish.y))):
        instance.graph.add_edge("enemy_base", instance.terrain[j][i], weight = 1.0)                       

    our_flag_node = regressions2.get_node_index(instance, instance.game.team.flag.position)
    enemy_score_node = regressions2.get_node_index(instance, instance.game.enemyTeam.flagScoreLocation)
    enemy_flag_node = regressions2.get_node_index(instance, instance.game.enemyTeam.flag.position)
    our_score_node = regressions2.get_node_index(instance, instance.game.team.flagScoreLocation)
    
    b_to_flag = nx.shortest_path(instance.graph, source="enemy_base", target = our_flag_node)
    b_to_def = nx.shortest_path(instance.graph, source="enemy_base", target = enemy_flag_node)
    b_to_def2 = nx.shortest_path(instance.graph, source="enemy_base", target = our_score_node)

    #Calculate how the enemy is exiting from their base.
    exit_paths = [(b_to_flag, 10), (b_to_def, 6), (b_to_def2, 2)]
    for x in range(50):
        position = instance.level.findRandomFreePositionInBox(instance.level.area)
        base_seperation = position - enemy_base
        base_seperation = base_seperation*15/base_seperation.length()
        close_pos = enemy_base + base_seperation
        x, y = regressions2.sanitize_position(instance, close_pos)
        close_pos = Vector2(x, y)
        node_index = regressions2.get_node_index(instance, close_pos)
        path = nx.shortest_path(instance.graph, source="enemy_base", target = node_index)
        exit_paths.append((path, 4))     
    return exit_paths

def put_exit_paths_in_graph(instance, exit_paths):
    enemy_base = get_enemy_base(instance)
    for path, weight in exit_paths:
        edgesinpath=zip(path[0:],path[1:])        
        for vt, vf in edgesinpath[:-1]:
            if "position" not in instance.graph.node[vf]:
                continue
            position = Vector2(*instance.graph.node[vf]["position"])
            if "position" not in instance.graph.node[vt]:
                continue
            next_position = Vector2(*instance.graph.node[vt]["position"])
            if position == next_position:
                continue
            x = position.x
            y = position.y
            instance.graph.node[regressions2.get_node_index(instance, Vector2(x,y))]["exit_path"] += 5.0*weight/(position.distance(enemy_base)**3+1)
    instance.graph.node["enemy_base"]["exit_path"] = 0.0
    
def get_close_nodes(instance):
    enemy_base = get_enemy_base(instance)
    
    close_nodes = set()
    enemy_base_normal_node = regressions2.get_node_index(instance, enemy_base)
    close_nodes.add(enemy_base_normal_node)
    
    #Calculate the weight of enemy exit squares.
    for x in range(25):
        addition_set = set()
        for node_index1 in close_nodes:
            neighbors = instance.graph.neighbors(node_index1)
            for node_index2 in neighbors:
                if node_index2 != None:
                    addition_set.add(node_index2)
        close_nodes = close_nodes.union(addition_set)    
    return close_nodes

def remove_spawn_nodes(instance, close_nodes):
    start, finish = instance.level.botSpawnAreas[instance.game.enemyTeam.name]
    for i, j in itertools.product(range(int(start.x), int(finish.x)), range(int(start.y), int(finish.y))):
        node_index = regressions2.get_node_index(instance, Vector2(i,j))
        if node_index in close_nodes:
            close_nodes.remove(node_index)
    return close_nodes

def weight_target_nodes(instance, close_nodes):        
    for node_index in close_nodes:
        if node_index == 0:
            continue
        instance.graph.node[node_index]["camp_target"] += instance.graph.node[node_index]["exit_path"]
        neighbors = instance.graph.neighbors(node_index)
        if neighbors != None:
            for neighbor in neighbors:
                if neighbor != 0 and neighbor != None:
                    instance.graph.node[neighbor]["camp_target"] += instance.graph.node[node_index]["exit_path"]


def weight_camp_locations_by_sight(instance, close_nodes):
    #Calculate the weight of all squares close to the enemy base relying on how many of the exit squares can be shot.
    enemy_base = get_enemy_base(instance)
    for node_index in close_nodes:
        node_position = regressions2.get_node_vector(instance, node_index)
        cells = []
        w = visibility.Wave((88, 50), lambda x, y: instance.level.blockHeights[x][y] > 1, lambda x, y: cells.append((x,y)))
        w.compute(node_position)    
        
        for x, y in cells:
            cell_position = Vector2(x, y)
            cell_node_index = regressions2.get_node_index(instance, cell_position)
            if node_position.distance(cell_position) < instance.level.firingDistance:
                #Edges don't work with our functions, and are unlikely to be actual optimum. #TODO fully debug rather than hack.
                if not (node_position.x < 1.0 or node_position.x > 87.0 or node_position.y < 1.0 or node_position.y > 47.0):
                    camp_value = instance.graph.node[cell_node_index]["camp_target"]/(cell_position.distance(enemy_base)+3)
                    instance.graph.node[node_index]["camp_location"] += camp_value        

def weight_camp_locations_by_base_exposure(instance):
    #Adjust the weight based on what squares can be seen from the enemy base.
    start, finish = instance.level.botSpawnAreas[instance.game.enemyTeam.name]
    for i, j in itertools.product(range(int(start.x), int(finish.x)), range(int(start.y), int(finish.y))):
        enemy_base_square = Vector2(i, j)
        cells = []
        w = visibility.Wave((88, 50), lambda x, y: instance.level.blockHeights[x][y] > 1, lambda x, y: cells.append((x,y)))
        w.compute(enemy_base_square)
        for x, y in cells:
            cell_position = Vector2(x, y)
            cell_node_index = regressions2.get_node_index(instance, cell_position)
            if cell_position.distance(enemy_base_square) < instance.level.firingDistance + 3:
                instance.graph.node[cell_node_index]["camp_location"] *= .8
    instance.graph.node["enemy_base"]["camp_location"] = 0.0

def  weight_camp_locations_by_choke_exposure(instance):
    for node in instance.choke_dict.keys():
        enemy_base_square = regressions2.get_node_vector(instance, node)
        cells = []
        w = visibility.Wave((88, 50), lambda x, y: instance.level.blockHeights[x][y] > 1, lambda x, y: cells.append((x,y)))
        w.compute(enemy_base_square)
        for x, y in cells:
            cell_position = Vector2(x, y)
            cell_node_index = regressions2.get_node_index(instance, cell_position)
            if cell_position.distance(enemy_base_square) < instance.level.firingDistance + 3:
                instance.graph.node[cell_node_index]["camp_location"] *= .8

    
    

def produce_best_camp_locations(instance, close_nodes):
    #Return best camping destinations to commander for use in action picking.
    camp_destinations = []
    for node in close_nodes:
        pair = (instance.graph.node[node]["camp_location"], node)
        camp_destinations.append(pair)
    camp_destinations.sort()
    camp_nodes = []
    for score, node in camp_destinations:
        camp_nodes.append(node)
    return_positions = []
    #Remove all nodes connected by 5 or less.
    for x in range(10):
        if len(camp_nodes) == 0:
            break
        node = camp_nodes.pop()
        neighbors = instance.graph.neighbors(node)
        for neighbor_node in neighbors:
            neighbors2 = instance.graph.neighbors(neighbor_node)
            for neighbor2 in neighbors2:
                neighbors3 = instance.graph.neighbors(neighbor2)
                for neighbor3 in neighbors3:
                    neighbors4 = instance.graph.neighbors(neighbor3)
                    for neighbor4 in neighbors4:
                        neighbors5 = instance.graph.neighbors(neighbor4)
                        for neighbor5 in neighbors5:
                            try:
                                camp_nodes.remove(neighbor5)
                            except ValueError:
                                pass
                        try:
                            camp_nodes.remove(neighbor4)
                        except ValueError:
                            pass
                    try:
                        camp_nodes.remove(neighbor3)
                    except ValueError:
                        pass   
                try:
                    camp_nodes.remove(neighbor2)
                except ValueError:
                    pass
            try:
                camp_nodes.remove(neighbor_node)
            except ValueError:
                pass
            
        return_positions.append(regressions2.get_node_vector(instance, node))
    if instance.DRAW_POINTS == "camp":
        instance.points = return_positions
    return return_positions

def update_choke_redundancy(instance):
    for bot_name in instance.bots.keys():
        real_bot = instance.get_bot_from_name(bot_name)
        if real_bot.state == 2:
            visible_cells = instance.bots[bot_name]["visibility"]
            for node in instance.choke_dict.keys():
                if node in visible_cells:
                    instance.choke_dict[node]["redundancy"] += 1

#####################################################################
#                       UTILITIES                                ####
#####################################################################


def get_enemy_base(instance):
    start, finish = instance.level.botSpawnAreas[instance.game.enemyTeam.name]
    enemy_base = Vector2(start.x, start.y).midPoint(Vector2(finish.x, finish.y))
    return enemy_base

def get_camp_command(instance, bot, command):
    #Get view direction intended to optimize enemy choke in sight. Calc total choke in sight. Return.
    if len(instance.bots[bot.name]["visibility"]) > 0.0:
        cells = instance.bots[bot.name]["visibility"]
    else:
        cells = regressions2.one_bot_visibility(instance, bot)

    #LEFT OFF - USE TO SCORE CHOKE POINTS
    master_chokes = instance.master_chokes.intersection(cells)
    choke_dict = instance.choke_dict


    nodes = [node for node in master_chokes]
    if len(nodes) == 0:
        nodes = [node for node in choke_dict.keys()]
        
    first_node = nodes.pop()
    x, y = instance.graph.node[node]["position"]
    cell_position = Vector2(x, y)
    total_mass = 0.0
    mass = instance.graph.node[first_node]["camp_target"]
    total_mass += mass
    center = mass * cell_position
    
    for cell_node in nodes:
        main_group_node = get_choke_group(instance, cell_node)
        #Weight nodes that are already targeted as less attractive to look at.
        if main_group_node != None:
            redundancy = choke_dict[main_group_node]["redundancy"]+1
        else:
            redundancy = 1.0
        
        x, y = instance.graph.node[cell_node]["position"]
        cell_position = Vector2(x, y)
        mass = instance.graph.node[cell_node]["camp_target"]/(redundancy*10)
        if cell_position.distance(bot.position) > instance.level.firingDistance or mass == 0.0:
            continue             
        center += cell_position * mass
        total_mass += mass
    if total_mass != 0.0:
        final_vector = center/total_mass
        look_vector = final_vector - bot.position
        #Using description to store power of defend command.
        command.facingDirection = look_vector
    return command

def get_choke_group(instance, cell_node):
    choke_group = None
    for node in instance.choke_dict.keys():
        if cell_node in instance.choke_dict[node]["nodes"]:
            choke_group = node
    return choke_group
