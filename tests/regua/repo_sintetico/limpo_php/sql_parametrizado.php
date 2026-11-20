<?php
$pdo = new PDO('mysql:host=db;dbname=loja', 'app', getenv('DB_PASS'));
$st = $pdo->prepare('SELECT * FROM produtos WHERE id = ?');
$st->execute([$_GET['id']]);
echo json_encode($st->fetchAll());
