<?php
$conn = mysqli_connect('db', 'app', getenv('DB_PASS'), 'loja');
$id = $_GET['id'];
$r = mysqli_query($conn, "SELECT * FROM produtos WHERE id = '" . $id . "'");
echo json_encode(mysqli_fetch_all($r));
