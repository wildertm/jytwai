import math, itertools, random
from api import vector2, Vector2, commands
#Third party modules
import networkx as nx
#KILLZONE modules
import visibility
from visualizer import VisualizerApplication


#################################################################################################
#                                       GRAPH BASED FEATURES                                    #
#################################################################################################

def enemy_sees_square(instance, bot, command): #TODO this is all wrong
    destination = command.target[0]
    for enemy_bot in instance.game.enemyTeam.members:
        if bot.seenlast < 2.0 and bot.health > 0.0:
            if can_bot_see(enemy_bot):
                return 1
    return 0

def enemy_shoots_path(instance, bot, command):
    #Use graph to calculate if any enemies can shoot any square in selected path.
    for waypoint in command.target:
        node_index = get_node_index(instance, waypoint)
        if instance.graph.node[node_index]["weight"] == 1.0:
            return 1
    else:
        return 0

#################################################################################################
#                UTILITY FUNCTIONS - MOST CODE HERE BY KILLZONE - NOT BY TWILDER                #
#################################################################################################

def evaluate_continue_present_command(instance, bot, command):
    if type(command) != commands.Defend:
        current_x = bot.position.x
        current_y = bot.position.y
        #Find roughly where we are in the bot's trajectory.
        for waypoint in command.target:
            total_error = waypoint.x - current_x + waypoint.y - current_y
            if abs(total_error) < 1.0: #TODO tweak to pick best of two closest nodes, this always picks the first and so thinks bots are farther away than they are.
                current_waypoint_index = command.target.index(waypoint)
                break
        #The rest of the bot's trajectory on the current plan
        future_waypoints = command.target[current_waypoint_index:]
        continue_command = type(command)(bot.name, future_waypoints, lookAt = command.lookAt, description = command.description)        

    if type(command) == commands.Defend:
        #For defend we don't need to reconstruct future path. The bot hasn't gone anywhere!
        pass
    
    value = instance.get_hueristic_value(bot, command)
    value += 2.5 #TODO figure out better way to calculate value of continuing command.
    return value

def enemy_shoots_square(instance, bot, command):
    destination = command.target[0]
    for enemy_bot in instance.game.enemyTeam.members:
        if enemy_bot.seenlast < 3.0 and enemy_bot.health > 0.0:
            if can_bot_shoot(instance, enemy_bot, destination):
                return 1
    return 0

def get_node_index(instance, position):
    i = int(position.x)
    j = int(position.y)
    #Fixes node 0 bug.
    if i == 0:
        i = 1
    if j == 0:
        j = 1
    width = instance.graph.graph["map_width"]
    #Node bug. #TODO find out real reason for bug instead of hacking solution.
    index = i + j*width
    if index in [2905, 2817, 1190, 1185, 4095]:
        index = i-1 + j*width
    return index

def get_node_vector(instance, node_index):
    position = instance.graph.node[node_index]["position"]
    x = position[0]
    y = position[1]
    return Vector2(x , y)

def get_path(instance, start, destination):
    start = get_node_index(instance, start)
    destination = get_node_index(instance, destination)
    path = nx.shortest_path(instance.graph, source = start, target = destination)
    #Convert list of node indexes to list of vectors for those nodes.
    for path_index in range(len(path)):
        node_index = path[path_index]
        node_vector = get_node_vector(instance, node_index)
        path[path_index] = node_vector
    return path

def update_visibility_graph(instance):
    #Turn all cells currently seen by enemies to 1 in graph.
    for bot in instance.game.enemyTeam.members:
        if bot.seenlast < 2.0 and bot.health > 0.0:
            cells = oneBotsVisibility(instance, bot)
            for cell in cells:
                cell_position = Vector2(cell[0], cell[1])
                index = getNodeIndex(instance, cell_position)
                if can_bot_shoot(instance, bot, cell_position):
                    change_node(instance, index, 1.0)

            for edge in instance.graph.edges():
                #Is the destination of the edge visible to enemies?
                #Set all edges with visible destinations to weight 1.0.
                if instance.graph.node[edge[1]]["weight"] == 1.0:
                    instance.graph.edge[edge[0]][edge[1]]["weight"] = 1.0
                else:
                    instance.graph.edge[edge[0]][edge[1]]["weight"] = .05
                    
def can_bot_see(instance, bot, position):
    position_to_bot_vector = position - bot.position
    angle = get_angle(bot.facingDirection, position_to_bot_vector)
    bot_fov = instance.level.fieldOfViewAngles[bot.state]
    if abs(angle) < bot_fov/2.0:
        return True
    else:
        return False

def can_bot_shoot(instance, bot, position):
    destination_to_bot = bot.position - position
    if can_bot_see(instance, bot, position) and destination_to_bot.length() < instance.level.firingDistance + 1:
        return True
    else:
        return False
                    
def reset_graph(instance):
    for node in instance.graph.nodes():
        instance.graph.node[node]["weight"] = 0
    for edge in instance.graph.edges():
        start = edge[0]
        end = edge[1]
        instance.graph.edge[start][end]["weight"] = 0

def get_angle(vector_a, vector_b):
    angle = math.acos(vector_a.dotProduct(vector_b)/(vector_a.length() * vector_b.length()))
    angle = angle
    return angle

def change_node(instance, node_index, weight):
    try:
        instance.graph.node[node_index]["weight"] = weight
    except:
        pass
        
def getNodeIndex(instance, position):
    i = int(position.x)
    j = int(position.y)
    width = instance.graph.graph["map_width"]
    return i+j*width

def oneBotsVisibility(instance, bot):
        position = bot.position
        cells = []
        w = visibility.Wave((88, 50), lambda x, y: instance.level.blockHeights[x][y] > 1, lambda x, y: cells.append((x, y)))
        w.compute(position)
        return cells

def makeGraph(instance):
        blocks = instance.level.blockHeights
        width, height = len(blocks), len(blocks[0])

        g = nx.Graph(directed=False, map_height = height, map_width = width)

        #Makes graph with nodes of all "blocks" in level
        instance.terrain = []
        for j in range(0, height):
            row = []
            for i in range(0,width):
                if blocks[i][j] == 0:
                    g.add_node(i+j*width, position = (float(i)+0.5, float(j)+0.5), weight = 0.0)
                    row.append(i+j*width)
                else:
                    row.append(None)
            instance.terrain.append(row)
            
        #Add edges for each possible adjacent combination
        for i, j in itertools.product(range(0, width), range(0, height)):
            p = instance.terrain[j][i]
            if not p: continue
    
            if i < width-1:
                q = instance.terrain[j][i+1]
                if q:
                    e = g.add_edge(p, q, weight = 1.0)    
            if j < height-1:
                r = instance.terrain[j+1][i]
                if r:
                    e = g.add_edge(p, r, weight = 1.0)
        #Fixes bug where many things had no path to node 0.
        neighbors = g.neighbors(0)
        for neigbor in neighbors:
            g.remove_edge(0, neighbor)
        g.remove_node(0)
        #Sets final graph as attribute to the Commander instance.
        instance.graph = g
        
        
def update_graph(instance):
    #0 all node and edge weights
    reset_graph(instance)
    #Set all nodes that are currently seen by enemies to 1. All edges that walk into them to 1.
    update_visibility_graph(instance)


#################################################################################################
#                GRAPHICS LOGIC - ALL CODE HERE BY KILLZONE - NOT BY TWILDER                  ###
#################################################################################################
def initialize_graphics(instance):
    from PySide import QtGui, QtCore
    def drawPreWorld(visualizer):
        brightest = max([instance.visibilities.pixel(i,j) for i, j in itertools.product(range(88), range(50))])

        for i, j in itertools.product(range(88), range(50)):            
            n = instance.terrain[j][i]
            if n:
                if instance.mode == instance.MODE_VISIBILITY:
                    d = instance.visibilities.pixel(i,j) * 255 / (brightest+1)
            else:                
                d = 32
            visualizer.drawPixel((i, j), QtGui.qRgb(d,d,d))
                
    def drawPreBots(visualizer):
        for p, _ in instance.ambushes:
            visualizer.drawCircle(p, QtGui.qRgb(255,255,0), 0.5)
            
    def keyPressed(e):
        if e.key() == QtCore.Qt.Key_Space:
            instance.mode = 1 - instance.mode

    #Main logic #!!!! REQUIRES INSTANCE TO HAVE GRAPH
    instance.mode = instance.MODE_VISIBILITY
    instance.visualizer = VisualizerApplication(instance)

    instance.visualizer.setDrawHookPreWorld(drawPreWorld)
    instance.visualizer.setDrawHookPreBots(drawPreBots)
    instance.visualizer.setKeyboardHook(keyPressed)

    makeGraph(instance)
    
##    instance.graph.add_node("enemy_base")
##    start, finish = instance.level.botSpawnAreas[instance.game.enemyTeam.name]        
##    for i, j in itertools.product(range(int(start.x), int(finish.x)), range(int(start.y), int(finish.y))):
##        instance.graph.add_edge("enemy_base", instance.terrain[j][i], weight = 1.0)            
##
##
##    instance.graph.add_node("base")
##    start, finish = instance.level.botSpawnAreas[instance.game.team.name]        
##    for i, j in itertools.product(range(int(start.x), int(finish.x)), range(int(start.y), int(finish.y))):
##        instance.graph.add_edge("base", instance.terrain[j][i],weight = 1.0)            
##
##
    
##    instance.node_EnemyFlagIndex = getNodeIndex(instance, instance.game.team.flag.position)
##    instance.node_EnemyScoreIndex = getNodeIndex(instance, instance.game.enemyTeam.flagScoreLocation)
    # instance.node_Bases = instance.graph.add_vertex()
    # e = instance.graph.add_edge(instance.node_Bases, instance.node_MyBase)
    # e = instance.graph.add_edge(instance.node_Bases, instance.node_EnemyBase)

##    vb2f = nx.shortest_path(instance.graph, source="enemy_base", target=instance.node_EnemyFlagIndex)
##    vf2s = nx.shortest_path(instance.graph, source=instance.node_EnemyFlagIndex, target=instance.node_EnemyScoreIndex)
    #vb2s = nx.shortest_path(instance.graph, source="enemy_base", target=instance.node_EnemyScoreIndex)

    #Coloration based on score in an 88 by 50 pixel grid?
    #Grid squares are set with setPixel(xcoord, ycoord, intRepresentingDarkness)
    instance.visibilities = QtGui.QImage(88, 50, QtGui.QImage.Format_ARGB32)
    instance.visibilities.fill(0)
    
##    #Path from enemy base to flag to scoring position.
##    path = vb2f + vf2s
##    #Zip returns a list of 0-nth tuples using ith items from each iterable.
##    #Each represents two graph node indexes, or an edge along the path.
##    edgesinpath = zip(path[0:], path[1:])
##    #Vt is the start node index, vf is the end note index.
##    for vt, vf in edgesinpath[:-1]:
##        if "position" not in instance.graph.node[vf]:
##            continue
##        position = Vector2(*instance.graph.node[vf]["position"])
##        if "position" not in instance.graph.node[vt]:
##            continue
##        next_position = Vector2(*instance.graph.node[vt]["position"])
##        if position == next_position:
##            continue
##        #Facing vector of the move on the graph.
##        orientation = (next_position - position).normalized()
##
##        #TODO swap to actual vector/sight range visibility calc.
##        def visible(p):
##            delta = (p-position)
##            l = delta.length()
##            if l > 20.0:
##                return False
##            if l < 2.5:
##                return True
##            delta /= l
##            return orientation.dotProduct(delta) >= 0.5
##
##        #List of points that are visible from a designated point.
##        cells = []
##        w = visibility.Wave((88, 50), lambda x, y: instance.level.blockHeights[x][y] > 1, lambda x, y: cells.append((x, y)))
##        w.compute(position)
##
##        #Increment the visibility int of each point that it has visibility to and sees by one.
##        for x, y in [c for c in cells if visible(Vector2(c[0]+0.5, c[1]+0.5))]:
##            instance.visibilities.setPixel(x, y, instance.visibilities.pixel(x, y)+1)
##
##    #Add weighted edges to graph
##    instance.node_EnemyBaseToFlagIndex = "enemy_base_to_flag"
##    instance.graph.add_node(instance.node_EnemyBaseToFlagIndex)
##    for vertex in vb2f:
##        instance.graph.add_edge(instance.node_EnemyBaseToFlagIndex, vertex, weight = 1.0)
##    
##    instance.node_EnemyFlagToScoreIndex = "enemy_flag_to_score" 
##    instance.graph.add_node(instance.node_EnemyFlagToScoreIndex)
##    for vertex in vf2s:
##        instance.graph.add_edge(instance.node_EnemyFlagToScoreIndex, vertex, weight = 1.0)
##    
##    instance.node_EnemyBaseToScoreIndex = "enemy_base_to_score"
##    instance.graph.add_node(instance.node_EnemyBaseToScoreIndex)
##
##    #Calculate shortest path to enemy flag from each point.
##    instance.distances = nx.single_source_shortest_path_length(instance.graph, instance.node_EnemyFlagToScoreIndex)
##    
##    instance.queue = {}
##    instance.index = 0
##
##    #Evaluates candidate points
##    def evaluate(position, orientation, callback):
##        #List of squares that can be seen from prospective position.
##        cells = []
##        w = visibility.Wave((88, 50), lambda x, y: instance.level.blockHeights[x][y] > 1, lambda x, y: cells.append((x,y)))
##        w.compute(position)
##
##        def visible(p):
##            delta = (p-position)
##            l = delta.length()
##            if l > 15.0:
##                return False
##            if l < 2.5:
##                return True
##            delta /= l
##            return orientation.dotProduct(delta) > 0.9238
##
##        total = 0.0
##        for x, y in [c for c in cells if visible(Vector2(c[0] + 0.5, c[1] + 0.5))]:
##            total += callback(x,y)
##        return total
    def evaluate(position, orientation, callback):
        return 1

    #Calculates points to be visualized, stores as "ambushes" which are visualized.        
    def calculatePOIS():        
        results = []
        for x in range(20):
            p = instance.level.findRandomFreePositionInBox(instance.level.area)
            o = Vector2(random.uniform(-0.5, 0.5), random.uniform(-0.5, 0.5)).normalized()
            s = evaluate(p, o, lambda x, y: 25.0)
            results.append((s, (p, o)))
        instance.ambushes = [r for _, r in results]
        
    calculatePOIS()

#################################################################################################
#        GRAPHICS UPDATES - HANDLES UPDATING VISUALS FOR VARIOUS FACTORS - BY TWILDER         ###
#################################################################################################

def update_graphics(instance):
    #Set all squares to darkness
    instance.visibilities.fill(0)
    #Set all values to the graph values.
    for node, dictionary in instance.graph.nodes_iter(data=True):
        x = dictionary["position"][0]
        y = dictionary["position"][1]
        weight =  dictionary["weight"]
        instance.visibilities.setPixel(x, y, weight)

def update_graphics_enemy_belief(instance, node_set_list):  
    #Set all squares to darkness
##    print node_list_list
    instance.visibilities.fill(0)
    for node_set in node_set_list:
        for node in node_set:
            x = instance.graph.node[node]["position"][0]
            y = instance.graph.node[node]["position"][1]
            instance.visibilities.setPixel(x, y, random.randrange(0,254))

def update_graphics_friendly_sight(instance):  
    instance.visibilities.fill(0)
    for node in instance.graph.nodes():
        if instance.graph.node[node]["friendly_sight"]:
            x = instance.graph.node[node]["position"][0]
            y = instance.graph.node[node]["position"][1]
            instance.visibilities.setPixel(x, y, 1.0)

def update_graphics_probability_enemy(instance):  
    instance.visibilities.fill(0)
    for node in instance.graph.nodes():
        x = instance.graph.node[node]["position"][0]
        y = instance.graph.node[node]["position"][1]
        p_enemy_on_node = instance.graph.node[node]["p_enemy"]
        instance.visibilities.setPixel(x, y, p_enemy_on_node * 254)
