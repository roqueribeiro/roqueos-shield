<?php
$host = $_GET['host'];
system("ping -c 1 " . $host);
