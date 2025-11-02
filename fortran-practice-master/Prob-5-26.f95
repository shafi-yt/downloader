program file_read_write
    implicit none
    integer :: smallest_int, largest_int, curr, iostat, i_count, &
                smallest_index, largest_index
    character(len=20) :: input_file 
    character(len=100) :: iomsg 

    write (*,*) 'Enter the input file name: '
    read (*,*) input_file 
    open(unit=10, file=input_file, status='old', iostat=iostat, iomsg=iomsg)
    if (iostat /= 0) then
        write (*,*) 'Error opening input file: ', trim(iomsg)
        stop
    end if 

    i_count = 0 
    smallest_int = huge(0)
    largest_int = -huge(0) 
    smallest_index = -1
    largest_index = -1

    do 
        read (10, *, iostat=iostat) curr
        if (iostat /= 0) then
            write (*,*) 'End of file or read error encountred.'
            exit
        end if
        i_count = i_count + 1 

        if (curr < smallest_int) then
            smallest_int = curr 
            smallest_index = i_count
        else if (curr > largest_int) then 
            largest_int = curr 
            largest_index = i_count
        end if 
    end do 

    write (*,'(A,1X,I0)') 'Smallest integer: ', smallest_int
    write (*,'(A,1x,I0)') 'Smallest integer occred at line: ', smallest_index

    write (*,'(A,1X,I0)') 'Largest integer: ', largest_int
    write (*,'(A,1X,I0)') 'Largest integer occred at line: ', largest_index

end program file_read_write