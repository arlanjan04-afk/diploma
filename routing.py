import numpy as np
from math import radians, sin, cos, sqrt, atan2
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
from simulator import DEPOT

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))

def build_distance_matrix(points):
    n = len(points)
    matrix = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i != j:
                matrix[i][j] = haversine(*points[i], *points[j])
    return (matrix * 1000).astype(int)

def optimize_route(containers_df):
    """Простой TSP — один мусоровоз без ограничения ёмкости (оставлен для совместимости)."""
    if len(containers_df) == 0:
        return [], 0
    
    points = [(DEPOT['lat'], DEPOT['lon'])]
    points += list(zip(containers_df['lat'], containers_df['lon']))
    
    matrix = build_distance_matrix(points)
    manager = pywrapcp.RoutingIndexManager(len(points), 1, 0)
    routing = pywrapcp.RoutingModel(manager)
    
    def dist_cb(from_idx, to_idx):
        return matrix[manager.IndexToNode(from_idx)][manager.IndexToNode(to_idx)]
    
    transit_idx = routing.RegisterTransitCallback(dist_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)
    
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.seconds = 5
    
    solution = routing.SolveWithParameters(params)
    if not solution:
        return [], 0
    
    route_order = []
    index = routing.Start(0)
    total = 0
    while not routing.IsEnd(index):
        route_order.append(manager.IndexToNode(index))
        prev = index
        index = solution.Value(routing.NextVar(index))
        total += routing.GetArcCostForVehicle(prev, index, 0)
    route_order.append(manager.IndexToNode(index))
    
    return _build_route_points(route_order, containers_df), total / 1000


def optimize_cvrp(containers_df, num_vehicles=2, vehicle_capacity=5000):
    """
    CVRP: несколько мусоровозов с ограничением ёмкости.
    
    Args:
        containers_df: DataFrame контейнеров с lat, lon, current_fill, capacity_liters
        num_vehicles: количество доступных мусоровозов
        vehicle_capacity: ёмкость одного мусоровоза в литрах
    
    Returns:
        routes: список маршрутов по машинам [[точки_машины_1], [точки_машины_2], ...]
        total_distance: общая дистанция в км
    """
    if len(containers_df) == 0:
        return [], 0
    
    # Точки: 0 = депо, далее контейнеры
    points = [(DEPOT['lat'], DEPOT['lon'])]
    points += list(zip(containers_df['lat'], containers_df['lon']))
    
    # Объём мусора в каждом контейнере = ёмкость × % заполнения
    demands = [0]  # депо
    for _, row in containers_df.iterrows():
        volume = int(row['capacity_liters'] * row['current_fill'] / 100)
        demands.append(volume)
    
    matrix = build_distance_matrix(points)
    
    manager = pywrapcp.RoutingIndexManager(len(points), num_vehicles, 0)
    routing = pywrapcp.RoutingModel(manager)
    
    def dist_cb(from_idx, to_idx):
        return matrix[manager.IndexToNode(from_idx)][manager.IndexToNode(to_idx)]
    
    transit_idx = routing.RegisterTransitCallback(dist_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)
    
    # Ограничение по ёмкости
    def demand_cb(from_idx):
        return demands[manager.IndexToNode(from_idx)]
    
    demand_idx = routing.RegisterUnaryTransitCallback(demand_cb)
    routing.AddDimensionWithVehicleCapacity(
        demand_idx,
        0,  # без запаса
        [vehicle_capacity] * num_vehicles,
        True,
        'Capacity'
    )
    
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.seconds = 10
    
    solution = routing.SolveWithParameters(params)
    if not solution:
        return [], 0
    
    routes = []
    total_distance = 0
    
    for vehicle_id in range(num_vehicles):
        index = routing.Start(vehicle_id)
        route_nodes = []
        route_load = 0
        route_dist = 0
        
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            route_nodes.append(node)
            route_load += demands[node]
            prev = index
            index = solution.Value(routing.NextVar(index))
            route_dist += routing.GetArcCostForVehicle(prev, index, vehicle_id)
        
        route_nodes.append(manager.IndexToNode(index))
        
        # Пропускаем маршруты, в которых только депо (машина не выезжала)
        if len(route_nodes) > 2:
            route_points = _build_route_points(route_nodes, containers_df)
            routes.append({
                'vehicle_id': vehicle_id + 1,
                'points': route_points,
                'distance_km': route_dist / 1000,
                'load_liters': route_load,
                'load_percent': round(route_load / vehicle_capacity * 100, 1)
            })
            total_distance += route_dist
    
    return routes, total_distance / 1000


def _build_route_points(node_indices, containers_df):
    """Преобразует индексы узлов в список точек с метаданными."""
    route_points = []
    for node in node_indices:
        if node == 0:
            route_points.append({
                'name': 'Автобаза',
                'address': 'Депо',
                'lat': DEPOT['lat'],
                'lon': DEPOT['lon'],
                'type': 'depot'
            })
        else:
            row = containers_df.iloc[node - 1]
            route_points.append({
                'name': row['name'],
                'address': row['address'],
                'lat': row['lat'],
                'lon': row['lon'],
                'current_fill': row['current_fill'],
                'capacity_liters': row.get('capacity_liters', 1100),
                'volume_liters': int(row.get('capacity_liters', 1100) * row['current_fill'] / 100),
                'type': 'container'
            })
    return route_points


def calculate_savings(containers_df, optimized_km):
    if len(containers_df) == 0:
        return 0, 0
    points = [(DEPOT['lat'], DEPOT['lon'])]
    points += list(zip(containers_df['lat'], containers_df['lon']))
    points.append((DEPOT['lat'], DEPOT['lon']))
    naive_km = sum(haversine(*points[i], *points[i+1]) for i in range(len(points)-1))
    savings = naive_km - optimized_km
    savings_pct = (savings / naive_km * 100) if naive_km > 0 else 0
    return naive_km, savings_pct